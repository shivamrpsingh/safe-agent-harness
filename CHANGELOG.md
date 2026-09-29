# Changelog

## 0.2.0

- `CostBudget` tracks dollars and GPU-minutes beside steps, tokens, and seconds. Models and tools report a cost per call. A breach raises `BudgetExceeded`. Caps default to unlimited, so existing `Budget(max_steps=...)` calls behave as before.
- Irreversible tools require `idempotency_key`. A missing or duplicate key is not executed and is traced as `idempotency_rejected`.
- `run(..., checkpoint=path)` writes the in-flight step to JSON. `Harness.resume(path)` continues that file, including seen idempotency keys.
- `OllamaClient` implements `ModelClient.step()`. Install it with `safe-agent-harness[ollama]`.
- `run(..., structured=True)` returns `RunResult` (answer, trace id, steps, cost, gpu minutes, status). `run()` without that flag still returns a string.

## 0.1.0

- First release: harness, risk tiers, approvals, sandbox, limits, output checks, tracing, and evals.
