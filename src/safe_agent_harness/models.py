"""Model adapters. The harness only depends on the ModelClient protocol."""

from __future__ import annotations

from typing import Any

# Dollars per million tokens: (input, output, cache read). Cache writes bill at 1.25x input.
# Anthropic first-party rates; check https://platform.claude.com/docs/en/about-claude/pricing.
_PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 0.30),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
# An unknown model is priced at the most expensive known rate, so a budget errs on the safe side.
_UNKNOWN = max(_PRICES.values(), key=lambda p: p[0] + p[1])
CACHE_WRITE_X = 1.25
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ModelRefused(RuntimeError):
    """The model declined (stop_reason "refusal"). The harness falls back to its next model."""


def _price(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0,
           cache_write: int = 0) -> float:
    pin, pout, pread = _PRICES.get(model, _UNKNOWN)
    dollars = input_tokens * pin + output_tokens * pout
    dollars += cache_read * pread + cache_write * pin * CACHE_WRITE_X
    return dollars / 1_000_000


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class AnthropicClient:
    """Claude via the Anthropic SDK. Needs `pip install safe-agent-harness[anthropic]`.

    effort:       "low" | "medium" | "high" | "xhigh" | "max"; sent as output_config.effort.
    cache_system: mark the system prompt for prompt caching (it is the stable prefix).
    fallbacks:    "default" turns on the server-side refusal fallback (beta endpoint).
    A refusal that survives raises ModelRefused, so the harness tries its next model.
    Thinking blocks come back in "raw"; the harness appends them unchanged on the next turn.
    """

    def __init__(self, model: str, max_tokens: int = 1024, client: Any = None, *,
                 effort: str | None = None, cache_system: bool = False,
                 fallbacks: str | None = None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client, self.name, self.max_tokens = client, model, max_tokens
        self.effort, self.cache_system, self.fallbacks = effort, cache_system, fallbacks

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        kwargs: dict[str, Any] = {"model": self.name, "max_tokens": self.max_tokens,
                                  "system": system, "messages": messages, "tools": tools}
        if self.cache_system and system:
            kwargs["system"] = [{"type": "text", "text": system,
                                 "cache_control": {"type": "ephemeral"}}]
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        if self.fallbacks:
            resp = self.client.beta.messages.create(**kwargs, betas=[FALLBACK_BETA],
                                                    fallbacks=self.fallbacks)
        else:
            resp = self.client.messages.create(**kwargs)
        if _field(resp, "stop_reason") == "refusal":
            details = _field(resp, "stop_details")
            raise ModelRefused(f"{self.name} declined ({_field(details, 'category', 'unknown')})")
        calls = [{"id": b.id, "name": b.name, "input": b.input}
                 for b in resp.content if b.type == "tool_use"]
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = resp.usage
        incoming, outgoing = usage.input_tokens, usage.output_tokens
        read = _field(usage, "cache_read_input_tokens", 0) or 0
        write = _field(usage, "cache_creation_input_tokens", 0) or 0
        served = _field(resp, "model", None) or self.name  # a fallback model bills at its rate
        return {"text": text, "tool_calls": calls, "raw": resp.content,
                "tokens": incoming + outgoing + read + write,
                "dollars": _price(served, incoming, outgoing, read, write), "gpu_minutes": 0.0}


class FakeModel:
    """Scripted model for tests, evals, and offline demos.

    Script items:
      "text"                -> final answer
      ("tool", {args})      -> one tool call
      [("t1", {}), ...]     -> several tool calls in one step
      Exception instance    -> raised (tests model fallback)
    The last item repeats if the script runs out.
    """

    def __init__(self, script: list, name: str = "fake", dollars: float = 0.0,
                 gpu_minutes: float = 0.0):
        self.script, self.name, self.i = script, name, 0
        self.dollars, self.gpu_minutes = dollars, gpu_minutes

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        item = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return {"text": item, "tool_calls": [], "tokens": 100,
                    "dollars": self.dollars, "gpu_minutes": self.gpu_minutes}
        calls = item if isinstance(item, list) else [item]
        return {"text": "", "tokens": 150, "dollars": self.dollars, "gpu_minutes": self.gpu_minutes,
                "tool_calls": [{"id": f"call_{self.i}_{n}", "name": c[0], "input": c[1]}
                               for n, c in enumerate(calls)]}


class OllamaClient:
    """Local Ollama chat. Needs `pip install safe-agent-harness[ollama]` unless a client is injected."""

    def __init__(self, model: str, client: Any = None, host: str = "http://127.0.0.1:11434",
                 dollars_per_minute: float = 0.0):
        self.name, self.client, self.host = model, client, host
        self.dollars_per_minute = dollars_per_minute

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        if self.client is None:
            import ollama
            self.client = ollama.Client(host=self.host)
        resp = self.client.chat(model=self.name, messages=[{"role": "system", "content": system}, *messages],
                                tools=tools or None)
        message = _field(resp, "message", {}) or {}
        raw_calls = _field(message, "tool_calls", []) or []
        calls = []
        for index, call in enumerate(raw_calls):
            fn = _field(call, "function", call)
            calls.append({
                "id": str(_field(call, "id", f"ollama_{index}")),
                "name": _field(fn, "name", ""),
                "input": _field(fn, "arguments", {}) or {},
            })
        tokens = int(_field(resp, "prompt_eval_count", 0) or 0) + int(_field(resp, "eval_count", 0) or 0)
        gpu_minutes = float(_field(resp, "total_duration", 0) or 0) / 60_000_000_000
        return {
            "text": _field(message, "content", "") or "",
            "tool_calls": calls,
            "tokens": tokens,
            "raw": resp,
            "dollars": gpu_minutes * self.dollars_per_minute,
            "gpu_minutes": gpu_minutes,
        }
