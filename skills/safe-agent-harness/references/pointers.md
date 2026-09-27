# Pointer reference

Load only the sections the routing table in `SKILL.md` points to.

P1 Harness · P2 Scope · P3 Least privilege · P4 Risk tiers · P5 Input distrust · P6 Sandbox ·
P7 Limits · P8 Output validation · P9 Observability · P10 Evals · P-all Review checklist

---

## P1 — Harness engineering

**What:** Everything around the model that turns reasoning into controlled action.
**Flow:** task → validate → model plans → tool through the gate → trace → feedback.
**API:** `Harness(models=[primary, backup], tools, ...)`, `TransientError`, `Tool(fallback=...)`.
**Checklist:**
- At least two models in the list for fallback
- Tools raise `TransientError` only for retryable failures (timeout, 429, 5xx)
- Flaky external tools declare a `fallback`
- New providers implement `ModelClient.step()` returning `text`, `tool_calls`, `tokens`, `raw`
**Mistake:** Safety rules that exist only in the system prompt.

## P2 — Narrow scope

**What:** One agent, one job.
**API:** `Harness(system=...)` and the contents of `ToolRegistry`.
**Checklist:**
- `system` states purpose and a never-do list
- Every registered tool traces back to the purpose
- Out-of-scope requests get a clear refusal
**Mistake:** A general agent with 20 tools that can't be tested.

## P3 — Least-privilege tools

**What:** Minimum access per tool, under the agent's own identity.
**API:** each tool function builds its own scoped client; strict Pydantic fields (`pattern=`, `gt=`, `le=`, `max_length=`).
**Checklist:**
- No shared, personal, or admin credentials
- Separate dev and prod keys, loaded from env or a vault
- Args models constrain every field (IDs by pattern, amounts by range)
**Mistake:** Using a developer's personal API key or a DB admin login.

## P4 — Action risk tiers

**What:** Gate each action by blast radius.
**API:** `risk=Risk.READ | WRITE | IRREVERSIBLE`; `approver=` on the harness.
Approvers: `deny_all` (default), `policy_approver(rules, escalate=...)`, `cli_approver`, `allow_all` (tests only).
Any approver exception is treated as a denial.
**Checklist:**
- Every tool tagged
- Production escalation goes to a real human channel (Slack, UI)
- Writes carry idempotency keys
**Decision rule:** "Can it be undone without contacting anyone?" No → `IRREVERSIBLE`.
**Mistake:** Sending emails or deleting records with no approval step.

## P5 — Input distrust

**What:** Web pages, files, emails, and RAG results may contain prompt injection.
**API:** `Tool(untrusted_output=True)` wraps output in a `<tool_output trust="untrusted">` block and
emits an `injection_suspected` trace event when `scan_injection` matches.
**Checklist:**
- Every external-content tool marked `untrusted_output=True`
- Permissions never depend on content
- Injection cases in the eval suite
**Mistake:** Believing the scanner is a complete defense. It's a signal; P3 and P4 are the defense.

## P6 — Sandboxed execution

**What:** Generated code runs in a disposable, isolated container.
**API:** `run_in_sandbox(code, timeout=10, use_docker=True, image=..., memory=..., cpus=...)`.
Docker flags: no network, read-only root, CPU/memory/PID caps, all capabilities dropped.
**Checklist:**
- `use_docker=True` outside local dev
- A custom image if packages are needed (don't enable network to install them)
- Output size capped
**Mistake:** `use_docker=False` in production. It is not a security boundary.

## P7 — Hard limits

**What:** Steps, tokens, time, and request rate enforced in code.
**API:** `budget=lambda: Budget(max_steps, max_tokens, max_seconds)`, `rate_limiter=RateLimiter(limit, window)`, env `AGENT_KILL_SWITCH=1`.
**Checklist:**
- Limits tuned from real traces
- Redis-backed `RateLimiter` and `SessionMemory` for multi-instance deployments
- Kill switch tested
**Mistake:** No step cap, so a confused agent loops and burns budget.

## P8 — Output validation

**What:** Nothing leaves the harness unchecked.
**API:** `OutputValidator(schema=Model, redact_kinds=None, block_on=["aws_key","api_key"], max_chars=8000)`.
Redacts email, phone, SSN, card numbers; blocks secrets; validates JSON against `schema`.
On rejection the harness degrades with "failed a safety check".
**Checklist:**
- Structured outputs use `schema=`
- Kinds that must never leave are in `block_on`
- Domain-specific checks added by wrapping the validator
**Mistake:** Writing raw model text straight into a DB or customer email.

## P9 — Observability and audit

**What:** Every run is reconstructable.
**API:** `Tracer(sink=callable)` — default goes to Python logging (`safe_agent_harness` logger).
`MemorySink` for tests. `FailureLog(path="failures.jsonl")` for the feedback loop.
Events: `run_start`, `tool_call`, `tool_result`, `tool_fallback`, `args_rejected`, `approval_granted`,
`approval_denied`, `injection_suspected`, `model_failed`, `degraded`, `run_end`.
**Checklist:**
- Sink wired to Langfuse, LangSmith, or OpenTelemetry
- Alerts on cost spikes, failure rate, and denials
- Weekly review of `FailureLog`, each finding turned into code
**Mistake:** Logging only final answers.

## P10 — Evals and red-teaming

**What:** Prove the agent is safe on every change.
**API:** `EvalCase(name, task, check(answer, sink) -> bool, tags, model_script)`,
`run_evals(make_harness, cases, threshold=0.95)` raises below threshold.
Use `FakeModel(script)` for deterministic harness tests; a real model for behavior evals.
**Mix:** ~60% normal, ~20% edge, ~20% adversarial (injection, bad args, out-of-scope, budget exhaustion, PII).
**Checklist:**
- Runs in CI on model, prompt, and tool changes
- Each production incident becomes a case
**Mistake:** Testing once in a demo and shipping.

---

## P-all — PR review checklist

**Blocking:**
- New tool without a Pydantic args model or `risk=`
- Irreversible action reachable with `allow_all` or without an approver
- Code execution outside `run_in_sandbox`, or `use_docker=False` in prod config
- Hardcoded or shared credentials
- External-content tool missing `untrusted_output=True`
- Harness without `budget` limits appropriate to the task

**Non-blocking:**
- New tool with no `EvalCase`
- Missing `fallback` for a flaky external tool
- No `OutputValidator` on an internal-only agent
