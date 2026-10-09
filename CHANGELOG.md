# Changelog

## Unreleased

- `AnthropicClient` prices every current Claude model: Fable 5.1/5, Opus 5.5/5/4.8/4.7/4.6, Sonnet 5.5/5/4.6/4.5, and Haiku 4.5.
  - Sonnet 5 was listed at $3/$15; it is $2/$10.
  - Cache reads and writes are billed. Writes cost 1.25x input.
  - The served model sets the price, so a fallback model bills at its own rate.
  - An unknown model is priced at the most expensive known rate, so budgets err on the safe side.
- `AnthropicClient(effort=..., cache_system=True, fallbacks="default")`:
  - `effort` is sent as `output_config.effort`.
  - `cache_system` adds a cache breakpoint on the system prompt.
  - `fallbacks="default"` turns on the server-side refusal fallback (beta endpoint).

  All three are off by default.
- A refusal raises `ModelRefused`, so the harness falls back to its next model instead of returning empty text.

## 0.2.0

- `CostBudget` tracks dollars and GPU-minutes beside steps, tokens, and seconds. Models and tools report a cost per call. A breach raises `BudgetExceeded`. Caps default to unlimited, so existing `Budget(max_steps=...)` calls behave as before.
- Irreversible tools require `idempotency_key`. A missing or duplicate key is not executed and is traced as `idempotency_rejected`.
- `run(..., checkpoint=path)` writes the in-flight step to JSON. `Harness.resume(path)` continues that file, including seen idempotency keys.
- `OllamaClient` implements `ModelClient.step()`. Install it with `safe-agent-harness[ollama]`.
- `run(..., structured=True)` returns `RunResult` (answer, trace id, steps, cost, gpu minutes, status). `run()` without that flag still returns a string.

## 0.1.0

- First release: harness, risk tiers, approvals, sandbox, limits, output checks, tracing, and evals.
