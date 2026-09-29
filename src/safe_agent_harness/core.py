"""Core harness: Agent = Model + Harness.

The model proposes actions. The harness validates, gates, sandboxes, limits,
traces, and fails honestly.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

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
    """Step, token, time, dollar, and GPU-minute cap. Also exported as CostBudget."""

    max_steps: int = 8
    max_tokens: int = 50_000
    max_seconds: float = 60.0
    max_dollars: float = math.inf
    max_gpu_minutes: float = math.inf
    steps: int = 0
    tokens: int = 0
    dollars: float = 0.0
    gpu_minutes: float = 0.0
    started: float = field(default_factory=time.time)

    def charge(
        self,
        tokens: int = 0,
        *,
        dollars: float = 0.0,
        gpu_minutes: float = 0.0,
        count_step: bool = True,
    ) -> None:
        if count_step:
            self.steps += 1
        self.tokens += tokens
        self.dollars += dollars
        self.gpu_minutes += gpu_minutes
        if self.steps > self.max_steps:
            raise BudgetExceeded(f"step limit {self.max_steps} reached")
        if self.tokens > self.max_tokens:
            raise BudgetExceeded(f"token limit {self.max_tokens} reached")
        if time.time() - self.started > self.max_seconds:
            raise BudgetExceeded(f"time limit {self.max_seconds}s reached")
        if self.dollars > self.max_dollars:
            raise BudgetExceeded(f"dollar limit {self.max_dollars} reached")
        if self.gpu_minutes > self.max_gpu_minutes:
            raise BudgetExceeded(f"gpu-minute limit {self.max_gpu_minutes} reached")

    def snapshot(self) -> dict:
        data = {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "max_dollars": self.max_dollars,
            "max_gpu_minutes": self.max_gpu_minutes,
            "steps": self.steps,
            "tokens": self.tokens,
            "dollars": self.dollars,
            "gpu_minutes": self.gpu_minutes,
            "started": self.started,
        }
        for key in ("max_dollars", "max_gpu_minutes"):
            if data[key] == math.inf:
                data[key] = None
        return data

    @classmethod
    def restore(cls, data: dict) -> Budget:
        values = dict(data)
        for key in ("max_dollars", "max_gpu_minutes"):
            if values.get(key) is None:
                values[key] = math.inf
        return cls(**values)


CostBudget = Budget


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
    dollars: float = 0.0
    gpu_minutes: float = 0.0

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
         untrusted_output: bool = False, dollars: float = 0.0,
         gpu_minutes: float = 0.0) -> Callable[[Callable], Tool]:
    """Decorator: @tool("lookup", "Look up an order", LookupArgs) def f(args): ..."""
    def wrap(fn: Callable) -> Tool:
        return Tool(name, description, args_model, fn, risk, fallback, untrusted_output,
                    dollars, gpu_minutes)
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


class RunResult(BaseModel):
    answer: str
    trace_id: str
    steps: int
    cost: float
    gpu_minutes: float
    status: Literal["ok", "degraded"]


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
        self._seen: dict[str, set[str]] = defaultdict(set)

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

    def _run_tool(self, trace_id: str, session_id: str, name: str, raw_args: dict,
                  budget: Budget, _depth: int = 0) -> str:
        t = self.tools.get(name)
        if t is None:
            return f"ERROR: unknown tool '{name}'"
        try:
            args = t.args_model(**raw_args)
        except ValidationError as e:
            self.tracer.event(trace_id, "args_rejected", tool=name)
            return f"ERROR: invalid arguments: {e.errors(include_url=False)}"

        key = ""
        if t.risk is Risk.IRREVERSIBLE:
            key = str(raw_args.get("idempotency_key") or "")
            if not key:
                self.tracer.event(trace_id, "idempotency_rejected", tool=name, reason="missing")
                return "ERROR: irreversible tool requires idempotency_key"
            if key in self._seen[session_id]:
                self.tracer.event(trace_id, "idempotency_rejected", tool=name, reason="duplicate")
                return "ERROR: duplicate idempotency_key"
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
                return self._run_tool(trace_id, session_id, t.fallback, raw_args, budget, _depth + 1)
            return f"ERROR: tool '{name}' failed: {e}"

        if t.risk is Risk.IRREVERSIBLE:
            self._seen[session_id].add(key)
        if t.dollars or t.gpu_minutes:
            budget.charge(0, dollars=t.dollars, gpu_minutes=t.gpu_minutes, count_step=False)
        if t.untrusted_output:  # P5
            hits = scan_injection(result)
            if hits:
                self.tracer.event(trace_id, "injection_suspected", tool=name, patterns=hits)
            result = wrap_tool_output(name, result)
        self.tracer.event(trace_id, "tool_result", tool=name, result=result[:300])
        return result

    def _result(self, answer: str, trace_id: str, budget: Budget, status: Literal["ok", "degraded"]) -> RunResult:
        return RunResult(answer=answer, trace_id=trace_id, steps=budget.steps, cost=budget.dollars,
                         gpu_minutes=budget.gpu_minutes, status=status)

    def _save(self, path: Path | None, state: dict) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(state)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(blob, encoding="utf-8")
        tmp.replace(path)

    def _state(self, trace_id: str, user_id: str, session_id: str, task: str,
               messages: list, budget: Budget, done: list[str], status: str, answer: str = "") -> dict:
        return {
            "trace_id": trace_id,
            "user_id": user_id,
            "session_id": session_id,
            "task": task,
            "messages": messages,
            "budget": budget.snapshot(),
            "done": done,
            "seen": {sid: sorted(keys) for sid, keys in self._seen.items()},
            "status": status,
            "answer": answer,
        }

    def _execute(self, user_id: str, session_id: str, task: str,
                 checkpoint: Path | None, resumed: dict | None) -> RunResult:
        if resumed:
            trace_id = resumed["trace_id"]
            budget = Budget.restore(resumed["budget"])
            done = list(resumed.get("done") or [])
            messages = list(resumed["messages"])
            for sid, keys in (resumed.get("seen") or {}).items():
                self._seen[sid].update(keys)
            if os.getenv(KILL_SWITCH_ENV) == "1":
                answer = self.degrade(trace_id, "agent temporarily disabled", done)
                return self._result(answer, trace_id, budget, "degraded")
        else:
            trace_id = uuid.uuid4().hex[:12]
            self.tracer.event(trace_id, "run_start", user=user_id, task=task[:200])
            budget, done = self.new_budget(), []
            messages = self.memory.history(session_id) + [{"role": "user", "content": task}]
            if os.getenv(KILL_SWITCH_ENV) == "1":
                answer = self.degrade(trace_id, "agent temporarily disabled", done)
                return self._result(answer, trace_id, budget, "degraded")
            if not self.rate.allow(user_id):
                answer = self.degrade(trace_id, "rate limit reached, try again shortly", done)
                return self._result(answer, trace_id, budget, "degraded")

        try:
            while True:
                out = self._model_step(trace_id, messages)
                budget.charge(out.get("tokens", 0), dollars=float(out.get("dollars") or 0),
                              gpu_minutes=float(out.get("gpu_minutes") or 0))

                if not out["tool_calls"]:
                    text = out["text"]
                    if self.output_validator:  # P8
                        text = self.output_validator(text)
                    self.memory.add(session_id, {"role": "user", "content": task})
                    self.memory.add(session_id, {"role": "assistant", "content": text})
                    self.tracer.event(trace_id, "run_end", steps=budget.steps, tokens=budget.tokens,
                                      dollars=budget.dollars, gpu_minutes=budget.gpu_minutes)
                    result = self._result(text, trace_id, budget, "ok")
                    self._save(checkpoint, self._state(trace_id, user_id, session_id, task,
                                                       messages, budget, done, "ok", text))
                    return result

                messages.append({"role": "assistant", "content": out.get("raw") or out["text"]})
                results = []
                for call in out["tool_calls"]:
                    res = self._run_tool(trace_id, session_id, call["name"], call["input"], budget)
                    done.append(f"{call['name']} -> {res[:60]}")
                    results.append({"type": "tool_result", "tool_use_id": call["id"], "content": res})
                messages.append({"role": "user", "content": results})
                self._save(checkpoint, self._state(trace_id, user_id, session_id, task,
                                                   messages, budget, done, "running"))

        except BudgetExceeded as e:
            self.failures.record(trace_id, "budget", str(e), {"task": task})
            return self._result(self.degrade(trace_id, str(e), done), trace_id, budget, "degraded")
        except OutputRejected as e:
            self.failures.record(trace_id, "output", str(e), {"task": task})
            return self._result(self.degrade(trace_id, "the response failed a safety check", done),
                                trace_id, budget, "degraded")
        except Exception as e:  # noqa: BLE001
            self.failures.record(trace_id, "run", str(e), {"task": task})
            return self._result(self.degrade(trace_id, "an internal error occurred", done),
                                trace_id, budget, "degraded")

    def run(self, user_id: str, session_id: str, task: str,
            checkpoint: str | Path | None = None, *, structured: bool = False) -> str | RunResult:
        result = self._execute(user_id, session_id, task,
                               Path(checkpoint) if checkpoint else None, None)
        return result if structured else result.answer

    def resume(self, path: str | Path, *, structured: bool = False) -> str | RunResult:
        file = Path(path)
        if not file.is_file():
            raise FileNotFoundError(path)
        state = json.loads(file.read_text(encoding="utf-8"))
        if state.get("status") == "ok":
            result = RunResult(answer=state.get("answer", ""), trace_id=state["trace_id"],
                               steps=state["budget"]["steps"], cost=state["budget"]["dollars"],
                               gpu_minutes=state["budget"]["gpu_minutes"], status="ok")
            return result if structured else result.answer
        result = self._execute(state["user_id"], state["session_id"], state["task"], file, state)
        return result if structured else result.answer
