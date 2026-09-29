"""Model adapters. The harness only depends on the ModelClient protocol."""

from __future__ import annotations

from typing import Any

_PRICES = {
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}


def _price(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = _PRICES.get(model, (3.0, 15.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class AnthropicClient:
    """Claude via the Anthropic SDK. Needs `pip install safe-agent-harness[anthropic]`."""

    def __init__(self, model: str, max_tokens: int = 1024, client: Any = None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client, self.name, self.max_tokens = client, model, max_tokens

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        resp = self.client.messages.create(model=self.name, max_tokens=self.max_tokens,
                                           system=system, messages=messages, tools=tools)
        calls = [{"id": b.id, "name": b.name, "input": b.input}
                 for b in resp.content if b.type == "tool_use"]
        text = "".join(b.text for b in resp.content if b.type == "text")
        incoming = resp.usage.input_tokens
        outgoing = resp.usage.output_tokens
        return {"text": text, "tool_calls": calls, "raw": resp.content,
                "tokens": incoming + outgoing, "dollars": _price(self.name, incoming, outgoing),
                "gpu_minutes": 0.0}


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
