"""Model adapters. The harness only depends on the ModelClient protocol."""

from __future__ import annotations

from typing import Any


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
        return {"text": text, "tool_calls": calls, "raw": resp.content,
                "tokens": resp.usage.input_tokens + resp.usage.output_tokens}


class FakeModel:
    """Scripted model for tests, evals, and offline demos.

    Script items:
      "text"                -> final answer
      ("tool", {args})      -> one tool call
      [("t1", {}), ...]     -> several tool calls in one step
      Exception instance    -> raised (tests model fallback)
    The last item repeats if the script runs out.
    """

    def __init__(self, script: list, name: str = "fake"):
        self.script, self.name, self.i = script, name, 0

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        item = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return {"text": item, "tool_calls": [], "tokens": 100}
        calls = item if isinstance(item, list) else [item]
        return {"text": "", "tokens": 150,
                "tool_calls": [{"id": f"call_{self.i}_{n}", "name": c[0], "input": c[1]}
                               for n, c in enumerate(calls)]}
