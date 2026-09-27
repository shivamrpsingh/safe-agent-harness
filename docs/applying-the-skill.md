# Applying the safe-agent-harness skill

Agent = Model + Harness. The model proposes actions. The harness decides what runs, records everything, and fails honestly. Safety rules live in code. A prompt alone cannot enforce them.

This note is the helper layer on top of the skill. The rules themselves stay in:

- [SKILL.md](../skills/safe-agent-harness/SKILL.md) — routing, library API, build order, exit checklist
- [pointers.md](../skills/safe-agent-harness/references/pointers.md) — P1–P10, read only the sections the routing table names
- [prompts.md](../skills/safe-agent-harness/references/prompts.md) — copy-paste prompts for each task
- [Slide deck](../slides/safe-agent-harness.pptx) — the same material, with speaker notes

Library: `pip install safe-agent-harness`, then `import safe_agent_harness as sah`. Working example: [examples/support_agent.py](../examples/support_agent.py).

## One-command setup

Run this in the root of the repo where you are building an agent. It installs the skill, the 7 slash commands, and the editor rules. Running it again is safe: if the `<!-- safe-agent-harness -->` marker is already in `CLAUDE.md` or `AGENTS.md`, that file is left as it is.

Right after this repo is on GitHub:

```bash
uvx --from git+https://github.com/shivamrpsingh/safe-agent-harness safe-agent-harness init
uvx --from git+https://github.com/shivamrpsingh/safe-agent-harness safe-agent-harness init --cursor
uvx --from git+https://github.com/shivamrpsingh/safe-agent-harness safe-agent-harness init --all
```

After a PyPI release, the short form is `uvx safe-agent-harness init`.

| Flag | What it writes |
|---|---|
| `--cursor` | `skills/safe-agent-harness/`, `.cursor/rules/safe-agent-harness.mdc`, `.cursor/commands/` (7 files) |
| `--claude` | `.claude/skills/safe-agent-harness/`, `.claude/commands/` (7 files), a marked block in `CLAUDE.md` |
| `--agents` | `skills/safe-agent-harness/`, a marked block in `AGENTS.md` (Codex, Copilot, Windsurf, Gemini CLI) |
| `--all` | All three |

`--path` points at a repo root other than the current directory. With no flag and a terminal, `init` asks which tools you use. With no flag and no terminal, it exits and tells you to pass a flag.

No `uv`? `pipx run safe-agent-harness init`, or `pip install safe-agent-harness` and then `safe-agent-harness init`.

## When to use it

Use the skill whenever the task involves an agent, even if you never say "safety" or "harness":

| If the task is... | Pointers | Use |
|---|---|---|
| Starting a new agent | 1, 2, 4 | `Harness`, `ToolRegistry`, `system=` |
| Adding or changing a tool | 3, 4, 5 | `@tool(...)`, Pydantic args, `risk=` |
| Tool sends, deletes, pays, or writes externally | 4 | `Risk.IRREVERSIBLE`, `policy_approver` |
| Agent reads web, files, email, or RAG | 5 | `untrusted_output=True` |
| Agent runs code or shell | 6 | `run_in_sandbox(use_docker=True)` |
| Cost, loops, or abuse | 7 | `Budget`, `RateLimiter`, `AGENT_KILL_SWITCH=1` |
| Output goes to a DB, API, or customer | 8 | `OutputValidator(schema=..., block_on=...)` |
| "What did the agent do?" | 9 | `Tracer(sink=...)`, `FailureLog(path=...)` |
| Model or prompt change, or a release | 10 | `EvalCase`, `run_evals(threshold=...)` |
| Flaky tools or a model outage | 1 | `TransientError`, `fallback=`, model list |
| A different LLM provider | 1 | implement `ModelClient.step()` |
| PR review of agent code | all | the whole API |

Also use it for MCP tools, function calling, agent loops, human-in-the-loop approval, and PII in agent output.

Risk tier, when the blast radius is unclear: ask "Can this be undone without contacting anyone?" Yes → `Risk.WRITE`. No → `Risk.IRREVERSIBLE`.

In Cursor, after `init --cursor`, type `/` for the commands or mention `@safe-agent-harness`. The rule also attaches when you edit agent or tool files. You can paste a prompt from [prompts.md](../skills/safe-agent-harness/references/prompts.md) and fill the angle brackets.

## How it applies while you build an agent

Follow this order. Each step is a pointer the skill already defines. Extend the library. Do not reimplement the loop, the approver, or the sandbox.

1. **Scope (P2).** Purpose and a never-do list in `system=`. One agent, one job. Every tool in the registry traces back to that purpose.
2. **Tools (P3, P4).** `@tool` with a strict Pydantic model and a `risk=` on each. Args constrain IDs, amounts, and lengths. Each tool uses its own scoped credential from the environment.
3. **Approvals (P4).** `policy_approver` for what policy can allow, and a human `escalate=` for anything above that. The default approver denies. An approver exception is a denial.
4. **Limits (P7).** `Budget` and `RateLimiter`. Confirm `AGENT_KILL_SWITCH=1` stops a run.
5. **Sandbox (P6).** Any code execution goes through `run_in_sandbox(use_docker=True)`. Subprocess mode is for local development.
6. **Untrusted input (P5).** `untrusted_output=True` on web, file, email, and RAG tools. Tool text is data. Permissions never depend on that text. `scan_injection` is a signal. Least privilege and approvals are the defense.
7. **Output (P8).** `OutputValidator` on the harness, with `schema=` when the output is structured.
8. **Tracing (P9).** `Tracer(sink=...)` pointed at a real backend. `FailureLog` so failures become code changes.
9. **Evals (P10).** 30–50 `EvalCase`s, including attacks. `run_evals(threshold=...)` in CI. Tests use `FakeModel` so they run offline.

### Slash commands

| Command | Does | Pointers |
|---|---|---|
| `/new-agent <description>` | Scaffolds a complete safe agent plus tests | 1, 2, 4, then the rest |
| `/add-tool <description>` | Adds a validated, risk-tiered tool plus eval cases | 3, 4, 5 |
| `/harden <path>` | Adds injection handling, sandbox, limits, output validation | 5, 6, 7, 8 |
| `/audit <path>` | Scores code against P1–P10 with evidence and a fix list | all |
| `/review-pr [diff]` | Blocking and non-blocking findings | all |
| `/evals <agent>` | Generates about 30 eval cases, including attacks, and a CI gate | 10 |
| `/debug-trace <trace>` | Explains a run and proposes a code-level fix | 9, 1 |

### Hard rules

- Give the agent its own scoped credentials. Keep admin and personal credentials off the agent.
- Irreversible actions need an approver that can say no.
- Retry a non-idempotent write only with an idempotency key.
- Execute generated code only inside `run_in_sandbox`, and use Docker outside local development.
- Keep secrets and raw PII out of prompts and traces.
- Return the real tool result. On failure the harness says what happened and returns a trace ID.
- Text from tools, documents, or the web is data.

### Exit checklist

Mark each item done, n/a, or TODO before you call the agent finished:

- [ ] Purpose and never-do list in `system=` (P2)
- [ ] Every tool has a strict schema and risk tier (P3, P4)
- [ ] Irreversible tools gated by a real approver (P4)
- [ ] Untrusted sources marked `untrusted_output=True` (P5)
- [ ] Code execution sandboxed with Docker (P6)
- [ ] Budget and rate limits set; kill switch tested (P7)
- [ ] `OutputValidator` on the harness (P8)
- [ ] Tracer sink is a real backend; failures persisted (P9)
- [ ] Eval suite with attack cases gates CI (P10)

## Worked application: the support agent

[examples/support_agent.py](../examples/support_agent.py) is a customer-support agent for one job: answer order questions and refund damaged orders. Run it with no API key:

```bash
pip install -e ".[dev]"
python examples/support_agent.py
```

The offline script walks one task, "Order A1 arrived broken, please refund it." Each step is a pointer:

| Step in the script | Pointer | What the harness does |
|---|---|---|
| `SYSTEM` states the purpose and a never-do list (no price changes, no other customers' data, no instructions found in pages) | P2 | `Harness(..., system=SYSTEM)` |
| `lookup_order` raises `TransientError` and names `fallback="lookup_order_cache"` | P1 | The harness calls the cache tool and records `tool_fallback` |
| `RefundArgs` constrains `order_id`, `amount` (`gt=0, le=1000`), and `reason` length | P3 | Bad args are rejected before the function runs |
| `refund` is `Risk.IRREVERSIBLE`. `policy_approver` allows `amount <= 50` and escalates the rest to `cli_approver` | P4 | The $42 refund is auto-approved. A larger one waits for a person |
| `fetch_policy_page` is `untrusted_output=True` and returns a planted "IGNORE PREVIOUS INSTRUCTIONS" | P5 | Output is wrapped as data and an `injection_suspected` event is traced |
| `calculate` calls `run_in_sandbox`. The example uses `use_docker=False` for a local demo | P6 | Production uses `use_docker=True` |
| `Budget(max_steps=6)` | P7 | The loop stops at the cap |
| `OutputValidator()` and a final answer that contains `jane@example.com` | P8 | The email is redacted before the answer is returned |
| Logging is configured and `agent.run(...)` emits trace events | P9 | You can reconstruct the run from the trace |

The same shape is what `/new-agent` should scaffold: a system string, a small registry, a risk tag and a Pydantic model on every tool, an approver, a budget, an output validator, and offline tests with `FakeModel`.

Eval example: [examples/eval_suite.py](../examples/eval_suite.py). Full pointer write-ups: [pointers.md](../skills/safe-agent-harness/references/pointers.md).
