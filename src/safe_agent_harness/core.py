"""Core harness: Agent = Model + Harness.

The model proposes actions. The harness validates, gates, sandboxes, limits,
traces, and fails honestly.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ValidationError

from .guards import OutputRejected, scan_injection, wrap_tool_output

log = logging.getLogger("safe_agent_harness")

KILL_SWITCH_ENV = "AGENT_KILL_SWITCH"


# ---------------------------------------------------------------- P9 tracing
class MemorySink:
    """Collects events in memory. Useful for tests and evals."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, record: str) -> None:
        self.events.append(json.loads(record))

    def of(self, kind: str) -> list[dict]:
        return [e for e in self.events if e["event"] == kind]


class Tracer:
    """Emits one JSON line per event. Point `sink` at Langfuse, OTel, etc."""

    def __init__(self, sink: Callable[[str], None] | None = None):
        self.sink = sink or (lambda line: log.info(line))

    def event(self, trace_id: str, kind: str, **data: Any) -> None:
        rec = {"ts": round(time.time(), 3), "trace_id": trace_id, "event": kind, **data}
        self.sink(json.dumps(rec, default=str))


class FailureLog:
    """Feedback loop. Keeps failures in memory, optionally appends to a file."""

    def __init__(self, path: str | None = None):
        self.path, self.items = path, []

    def record(self, trace_id: str, where: str, error: str, context: dict) -> None:
        item = {"trace_id": trace_id, "where": where, "error": error, "context": context}
        self.items.append(item)
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(item, default=str) + "\n")


# ---------------------------------------------------------------- memory
class SessionMemory:
    """Per-session, bounded history. Swap for Redis in multi-instance setups."""

    def __init__(self, max_turns: int = 20):
        self._store: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_turns))

    def history(self, session_id: str) -> list[dict]:
        return list(self._store[session_id])

    def add(self, session_id: str, message: dict) -> None:
        self._store[session_id].append(message)


# ---------------------------------------------------------------- P7 limits
class BudgetExceeded(Exception):
    pass


@dataclass
class Budget:
    max_steps: int = 8
    max_tokens: int = 50_000
    max_seconds: float = 60.0
    steps: int = 0
    tokens: int = 0
    started: float = field(default_factory=time.time)

    def charge(self, tokens: int = 0) -> None:
        self.steps += 1
        self.tokens += tokens
        if self.steps > self.max_steps:
            raise BudgetExceeded(f"step limit {self.max_steps} reached")
        if self.tokens > self.max_tokens:
            raise BudgetExceeded(f"token limit {self.max_tokens} reached")
        if time.time() - self.started > self.max_seconds:
            raise BudgetExceeded(f"time limit {self.max_seconds}s reached")


class RateLimiter:
    """Sliding window per user. Swap for Redis in multi-instance setups."""

    def __init__(self, limit: int = 10, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, user_id: str) -> bool:
        now, hits = time.time(), self._hits[user_id]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


# ---------------------------------------------------------------- P3/P4 tools
class Risk(str, Enum):
    READ = "read"
    WRITE = "write"
    IRREVERSIBLE = "irreversible"


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[BaseModel], Any]
    risk: Risk = Risk.READ
    fallback: str | None = None
    untrusted_output: bool = False  # P5: True for web, files, email, RAG

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.args_model.model_json_schema()}


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict]:
        return [t.spec() for t in self._tools.values()]

    def __iter__(self):
        return iter(self._tools.values())


def tool(name: str, description: str, args_model: type[BaseModel], *,
         risk: Risk = Risk.READ, fallback: str | None = None,
         untrusted_output: bool = False) -> Callable[[Callable], Tool]:
    """Decorator: @tool("lookup", "Look up an order", LookupArgs) def f(args): ..."""
    def wrap(fn: Callable) -> Tool:
        return Tool(name, description, args_model, fn, risk, fallback, untrusted_output)
    return wrap


# ---------------------------------------------------------------- P1 retry
class TransientError(Exception):
    """Raise for timeouts, 429s, 5xx: things worth retrying."""


def call_with_retry(fn: Callable[[], Any], attempts: int = 3, base: float = 0.5) -> Any:
    for i in range(attempts):
        try:
            return fn()
        except TransientError:
            if i == attempts - 1:
                raise
            time.sleep(base * (2 ** i) + random.uniform(0, base))


# ---------------------------------------------------------------- models
class ModelClient(Protocol):
    name: str

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        """Return {"text": str, "tool_calls": [{"id","name","input"}], "tokens": int, "raw": Any}"""


# ---------------------------------------------------------------- harness
Approver = Callable[[str, dict], bool]


class Harness:
    def __init__(self, models: list[ModelClient], tools: ToolRegistry, *,
                 approver: Approver | None = None,
                 system: str = "You are a helpful agent. Use tools when needed.",
                 output_validator: Callable[[str], str] | None = None,
                 budget: Callable[[], Budget] = Budget,
                 rate_limiter: RateLimiter | None = None,
                 memory: SessionMemory | None = None,
                 tracer: Tracer | None = None,
                 failures: FailureLog | None = None,
                 retry_base: float = 0.5):
        if not models:
            raise ValueError("at least one model is required")
        self.models, self.tools, self.system = models, tools, system
        self.approver: Approver = approver or (lambda name, args: False)  # deny by default
        self.output_validator = output_validator
        self.new_budget = budget
        self.rate = rate_limiter or RateLimiter()
        self.memory = memory or SessionMemory()
        self.tracer = tracer or Tracer()
        self.failures = failures or FailureLog()
        self.retry_base = retry_base

    # P1 / P4 of the reel: graceful degradation
    def degrade(self, trace_id: str, reason: str, done: list[str]) -> str:
        self.tracer.event(trace_id, "degraded", reason=reason)
        summary = "; ".join(done[-3:]) if done else "nothing yet"
        if len(done) > 3:
            summary = f"{len(done)} actions, last: {summary}"
        return (f"I couldn't fully complete this ({reason}). "
                f"Completed so far: {summary}. Reference: {trace_id}")

    def _retry(self, fn):
        return call_with_retry(fn, base=self.retry_base)

    def _model_step(self, trace_id: str, messages: list[dict]) -> dict:
        last = None
        for model in self.models:
            try:
                return self._retry(lambda: model.step(self.system, messages, self.tools.specs()))
            except Exception as e:  # noqa: BLE001 - any model failure triggers fallback
                last = e
                self.tracer.event(trace_id, "model_failed", model=model.name, error=str(e))
        raise RuntimeError(f"all models failed: {last}")

    def _run_tool(self, trace_id: str, name: str, raw_args: dict, _depth: int = 0) -> str:
        t = self.tools.get(name)
        if t is None:
            return f"ERROR: unknown tool '{name}'"
        try:
            args = t.args_model(**raw_args)
        except ValidationError as e:
            self.tracer.event(trace_id, "args_rejected", tool=name)
            return f"ERROR: invalid arguments: {e.errors(include_url=False)}"

        if t.risk is Risk.IRREVERSIBLE:
            try:
                ok = bool(self.approver(name, raw_args))
            except Exception as e:  # noqa: BLE001 - approver failure = deny
                ok = False
                self.tracer.event(trace_id, "approver_error", tool=name, error=str(e))
            if not ok:
                self.tracer.event(trace_id, "approval_denied", tool=name, args=raw_args)
                return "DENIED: this action requires human approval and was not approved."
            self.tracer.event(trace_id, "approval_granted", tool=name)

        self.tracer.event(trace_id, "tool_call", tool=name, risk=t.risk.value, args=raw_args)
        try:
            result = str(self._retry(lambda: t.fn(args)))
        except Exception as e:  # noqa: BLE001
            self.failures.record(trace_id, f"tool:{name}", str(e), raw_args)
            if t.fallback and _depth < 2:
                self.tracer.event(trace_id, "tool_fallback", frm=name, to=t.fallback)
                return self._run_tool(trace_id, t.fallback, raw_args, _depth + 1)
            return f"ERROR: tool '{name}' failed: {e}"

        if t.untrusted_output:  # P5
            hits = scan_injection(result)
            if hits:
                self.tracer.event(trace_id, "injection_suspected", tool=name, patterns=hits)
            result = wrap_tool_output(name, result)
        self.tracer.event(trace_id, "tool_result", tool=name, result=result[:300])
        return result

    def run(self, user_id: str, session_id: str, task: str) -> str:
        trace_id = uuid.uuid4().hex[:12]
        self.tracer.event(trace_id, "run_start", user=user_id, task=task[:200])

        if os.getenv(KILL_SWITCH_ENV) == "1":
            return self.degrade(trace_id, "agent temporarily disabled", [])
        if not self.rate.allow(user_id):
            return self.degrade(trace_id, "rate limit reached, try again shortly", [])

        budget, done = self.new_budget(), []
        messages = self.memory.history(session_id) + [{"role": "user", "content": task}]

        try:
            while True:
                out = self._model_step(trace_id, messages)
                budget.charge(out.get("tokens", 0))

                if not out["tool_calls"]:
                    text = out["text"]
                    if self.output_validator:  # P8
                        text = self.output_validator(text)
                    self.memory.add(session_id, {"role": "user", "content": task})
                    self.memory.add(session_id, {"role": "assistant", "content": text})
                    self.tracer.event(trace_id, "run_end", steps=budget.steps, tokens=budget.tokens)
                    return text

                messages.append({"role": "assistant", "content": out.get("raw") or out["text"]})
                results = []
                for call in out["tool_calls"]:
                    res = self._run_tool(trace_id, call["name"], call["input"])
                    done.append(f"{call['name']} -> {res[:60]}")
                    results.append({"type": "tool_result", "tool_use_id": call["id"], "content": res})
                messages.append({"role": "user", "content": results})

        except BudgetExceeded as e:
            self.failures.record(trace_id, "budget", str(e), {"task": task})
            return self.degrade(trace_id, str(e), done)
        except OutputRejected as e:
            self.failures.record(trace_id, "output", str(e), {"task": task})
            return self.degrade(trace_id, "the response failed a safety check", done)
        except Exception as e:  # noqa: BLE001
            self.failures.record(trace_id, "run", str(e), {"task": task})
            return self.degrade(trace_id, "an internal error occurred", done)
