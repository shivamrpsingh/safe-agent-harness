"""AnthropicClient: current prices, cache billing, effort, prompt caching, refusals and fallbacks.

A fake SDK object stands in for `anthropic.Anthropic()`; nothing here calls the network.
"""

from types import SimpleNamespace

import pytest

from safe_agent_harness import AnthropicClient, ModelRefused
from safe_agent_harness.models import _PRICES, _price


def response(stop="end_turn", model="claude-opus-5-5", cache_read=0, cache_write=0):
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000,
                            cache_read_input_tokens=cache_read,
                            cache_creation_input_tokens=cache_write)
    text = SimpleNamespace(type="text", text="done")
    return SimpleNamespace(content=[text], usage=usage, stop_reason=stop, model=model,
                           stop_details=SimpleNamespace(category="cyber") if stop == "refusal" else None)


class FakeSDK:
    def __init__(self, resp):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._beta))
        self.resp = resp

    def _create(self, **kw):
        self.calls.append(("messages", kw))
        return self.resp

    def _beta(self, **kw):
        self.calls.append(("beta", kw))
        return self.resp


def test_opus_5_5_is_priced_at_4_and_20():
    out = AnthropicClient("claude-opus-5-5", client=FakeSDK(response())).step("s", [], [])
    assert out["dollars"] == pytest.approx(24.0)


def test_sonnet_5_is_priced_at_2_and_10():
    assert _price("claude-sonnet-5", 1_000_000, 1_000_000) == pytest.approx(12.0)


def test_an_unknown_model_is_priced_at_the_most_expensive_rate():
    top = max(_PRICES.values(), key=lambda p: p[0] + p[1])
    assert _price("claude-next-9", 1_000_000, 1_000_000) == pytest.approx(top[0] + top[1])


def test_cache_reads_and_writes_are_billed():
    sdk = FakeSDK(response(cache_read=1_000_000, cache_write=1_000_000))
    out = AnthropicClient("claude-opus-5-5", client=sdk).step("s", [], [])
    # 4 in + 20 out + 0.20 cache read + 5.00 cache write (1.25x input)
    assert out["dollars"] == pytest.approx(29.2)
    assert out["tokens"] == 4_000_000


def test_the_served_model_sets_the_price():
    sdk = FakeSDK(response(model="claude-haiku-4-5"))
    out = AnthropicClient("claude-opus-5-5", client=sdk).step("s", [], [])
    assert out["dollars"] == pytest.approx(6.0)


def test_effort_and_system_caching_are_sent():
    sdk = FakeSDK(response())
    AnthropicClient("claude-opus-5-5", client=sdk, effort="high", cache_system=True).step("rules", [], [])
    where, kw = sdk.calls[0]
    assert where == "messages"
    assert kw["output_config"] == {"effort": "high"}
    assert kw["system"] == [{"type": "text", "text": "rules", "cache_control": {"type": "ephemeral"}}]


def test_defaults_send_neither():
    sdk = FakeSDK(response())
    AnthropicClient("claude-opus-5-5", client=sdk).step("rules", [], [])
    _, kw = sdk.calls[0]
    assert "output_config" not in kw and kw["system"] == "rules"


def test_fallbacks_use_the_beta_endpoint():
    sdk = FakeSDK(response())
    AnthropicClient("claude-opus-5-5", client=sdk, fallbacks="default").step("s", [], [])
    where, kw = sdk.calls[0]
    assert where == "beta"
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]


def test_a_refusal_raises_so_the_harness_falls_back():
    client = AnthropicClient("claude-opus-5-5", client=FakeSDK(response(stop="refusal")))
    with pytest.raises(ModelRefused, match="cyber"):
        client.step("s", [], [])
