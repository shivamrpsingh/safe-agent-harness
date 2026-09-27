# safe-agent-harness

**Build LLM agents that can't quietly do damage.** A small Python library plus an AI-coding
skill that gives any agent risk-tiered tools, human approval for irreversible actions,
sandboxed code execution, cost and loop limits, prompt-injection signals, PII redaction,
full tracing, and an eval harness.

> Agent = Model + Harness. The model proposes. The harness decides what runs.

- **Library:** `pip install safe-agent-harness`, works with Claude or any model
- **Skill:** drop-in `SKILL.md` that teaches Claude Code, Cursor, Codex, Copilot, and other AI dev tools to build agents this way
- **Setup:** `uvx safe-agent-harness init` wires it into Claude Code, Cursor, or AGENTS.md in one step
- **Commands:** `/new-agent`, `/add-tool`, `/harden`, `/audit`, `/review-pr`, `/evals`, `/debug-trace`

Only dependency: Pydantic. MIT licensed.

---

## Why

Most agent failures aren't model failures. They're harness failures: a tool with admin
credentials, a refund with no approval, generated code on the host, a loop with no cap,
a web page that says "ignore previous instructions". This library puts those controls in
code, where a prompt can't talk its way around them.

## The 10 pointers

| # | Pointer | What the library gives you |
|---|---|---|
| 1 | Harness engineering | `Harness` with retries, tool fallbacks, model fallbacks, honest degradation |
| 2 | Narrow scope | `system=` purpose and never-do list; small `ToolRegistry` |
| 3 | Least privilege | Strict Pydantic args per tool, validated before anything runs |
| 4 | Risk tiers | `Risk.READ / WRITE / IRREVERSIBLE`, approvers that fail closed |
| 5 | Input distrust | `untrusted_output=True` wraps content as data and flags injection |
| 6 | Sandboxing | `run_in_sandbox()` in Docker: no network, read-only, capped |
| 7 | Hard limits | `Budget`, `RateLimiter`, `AGENT_KILL_SWITCH` |
| 8 | Output validation | `OutputValidator`: schema, PII redaction, secret blocking |
| 9 | Observability | `Tracer` JSON events, `FailureLog` feedback loop |
| 10 | Evals | `EvalCase`, `run_evals(threshold=...)` as a CI gate |

---

## Quick start (library)

```bash
pip install safe-agent-harness            # core
pip install "safe-agent-harness[anthropic]"  # + Claude adapter
```

```python
from pydantic import BaseModel, Field
from safe_agent_harness import (Harness, ToolRegistry, tool, Risk, Budget,
                                policy_approver, cli_approver, OutputValidator,
                                AnthropicClient)

class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^[A-Z]\d{1,6}$")
    amount: float = Field(gt=0, le=1000)

@tool("refund", "Refund an order", RefundArgs, risk=Risk.IRREVERSIBLE)
def refund(a: RefundArgs):
    return payments.refund(a.order_id, a.amount)      # your scoped client

agent = Harness(
    models=[AnthropicClient("claude-sonnet-5"), AnthropicClient("claude-haiku-4-5-20251001")],
    tools=ToolRegistry([refund]),
    system="You handle refunds for damaged orders. Never change prices.",
    approver=policy_approver({"refund": lambda a: a["amount"] <= 50}, escalate=cli_approver),
    output_validator=OutputValidator(),
    budget=lambda: Budget(max_steps=6),
)

print(agent.run(user_id="u1", session_id="s1", task="Order A1 arrived broken, refund it"))
```

Refunds of $50 or less run automatically. Larger ones ask a human. If anything fails,
the agent says what happened and returns a trace ID instead of inventing a result.

### Try it without an API key

```bash
git clone https://github.com/shivamrpsingh/safe-agent-harness && cd safe-agent-harness
pip install -e ".[dev]"
python examples/support_agent.py        # scripted run, prints every trace event
cd examples && python eval_suite.py     # 5 eval cases incl. attacks, CI-style exit code
pytest -q                               # 15 tests
```

The support agent demonstrates a DB outage falling back to a cache, a planted prompt
injection being flagged, sandboxed arithmetic, an auto-approved refund, and a customer
email redacted from the answer.

Live with Claude: `export ANTHROPIC_API_KEY=...` then
`python examples/support_agent.py --live "Refund order A1, it arrived broken"`.

---

## Use it as a skill in your AI coding tool

The skill teaches your assistant to build agents with this library and these rules.
It activates automatically on agent-related work, or you can call it directly.

### One command (recommended)

Run this in the root of the repo where you're building an agent:

```bash
uvx safe-agent-harness init            # asks which tools you use
uvx safe-agent-harness init --all      # Claude Code + Cursor + AGENTS.md
uvx safe-agent-harness init --cursor   # or --claude, --agents
```

Before the PyPI release, install straight from GitHub:
`uvx --from git+https://github.com/shivamrpsingh/safe-agent-harness safe-agent-harness init`

No `uv`? Use `pipx run safe-agent-harness init`, or `pip install safe-agent-harness`
and then `safe-agent-harness init`. Safe to rerun: it won't duplicate entries.

### Guide and slides

- [Applying the skill](docs/applying-the-skill.md) — when to use it, how it applies while you build an agent, and a walkthrough of the support agent
- [Slide deck](slides/safe-agent-harness.pptx) — the same material, with speaker notes on every slide

### Manual install

<details><summary>Claude Code</summary>

```bash
mkdir -p .claude/skills .claude/commands
cp -r skills/safe-agent-harness .claude/skills/
cp commands/*.md .claude/commands/
cat adapters/CLAUDE.md.snippet >> CLAUDE.md
```

Call it:
```
/new-agent a support agent that looks up orders and issues refunds
/add-tool send_invoice that emails an invoice through SendGrid
/audit src/agents/
```
Or just ask: "Use the safe-agent-harness skill to add a web search tool."
</details>

<details><summary>Cursor</summary>


```bash
mkdir -p .cursor/rules .cursor/commands
cp adapters/cursor-rule.mdc .cursor/rules/safe-agent-harness.mdc
cp commands/*.md .cursor/commands/
```
Keep `skills/safe-agent-harness/` in the repo root; the rule points there. The rule
auto-attaches when you edit agent or tool files. Type `/` in chat for the commands, or
mention `@safe-agent-harness`.
</details>

<details><summary>Codex, GitHub Copilot, Windsurf, Gemini CLI, others</summary>

```bash
cat adapters/AGENTS.md.snippet >> AGENTS.md
# Copilot without AGENTS.md support:
# cat adapters/AGENTS.md.snippet >> .github/copilot-instructions.md
```
Then prompt: "Using safe-agent-harness, harden src/agent.py."
</details>

Copy-paste prompts for every task are in `skills/safe-agent-harness/references/prompts.md`.

### Available skill commands

| Command | Does | Pointers |
|---|---|---|
| `/new-agent <description>` | Scaffolds a complete safe agent plus tests | 1, 2, 4 → all |
| `/add-tool <description>` | Adds a validated, risk-tiered tool plus eval cases | 3, 4, 5 |
| `/harden <path>` | Adds injection handling, sandbox, limits, output validation | 5, 6, 7, 8 |
| `/audit <path>` | Scores code against P1–P10 with evidence and a fix list | all |
| `/review-pr [diff]` | Blocking and non-blocking findings per the review checklist | all |
| `/evals <agent>` | Generates 30 eval cases incl. attacks and a CI gate | 10 |
| `/debug-trace <trace>` | Explains a run and proposes a code-level fix | 9, 1 |

### How the skill routes a request

```
your prompt or /command
        │
        ▼
adapter (CLAUDE.md / .cursor rule / AGENTS.md) ──► SKILL.md routing table
        │
        ├─► references/pointers.md  (only the matching P# sections)
        ├─► safe_agent_harness API   (classes to use)
        └─► exit checklist           (proof it's done)
```

---

## API reference

| Object | Purpose |
|---|---|
| `Harness(models, tools, *, approver, system, output_validator, budget, rate_limiter, memory, tracer, failures)` | The agent loop with every control applied |
| `Harness.run(user_id, session_id, task) -> str` | Run one task; never raises, degrades honestly |
| `@tool(name, description, ArgsModel, risk=, fallback=, untrusted_output=)` | Define a tool |
| `Risk.READ / WRITE / IRREVERSIBLE` | Action tiers; irreversible needs approval |
| `deny_all`, `allow_all`, `cli_approver`, `policy_approver(rules, escalate)` | Approvers (fail closed) |
| `run_in_sandbox(code, use_docker=True, ...)` | Isolated code execution |
| `Budget(max_steps, max_tokens, max_seconds)`, `RateLimiter(limit, window)` | Limits |
| `OutputValidator(schema, redact_kinds, block_on, max_chars)` | Output checks |
| `scan_injection(text)`, `redact(text)`, `wrap_tool_output(name, text)` | Guard helpers |
| `Tracer(sink)`, `MemorySink`, `FailureLog(path)` | Observability |
| `EvalCase`, `run_evals(make_harness, cases, threshold)` | Evals |
| `AnthropicClient(model)`, `FakeModel(script)` | Model adapters |

**Other providers:** implement one method.
```python
class MyModel:
    name = "my-model"
    def step(self, system, messages, tools) -> dict:
        return {"text": "...", "tool_calls": [{"id": "...", "name": "...", "input": {...}}],
                "tokens": 123, "raw": None}
```

---

## Production checklist

- `approver` wired to a real human channel (Slack, UI). It denies by default.
- `run_in_sandbox(use_docker=True)`. The subprocess mode is for development only.
- Redis-backed `RateLimiter` and `SessionMemory` when running more than one instance.
- `Tracer(sink=...)` sending to Langfuse, LangSmith, or OpenTelemetry.
- `run_evals(threshold=...)` in CI.

## Limitations

`scan_injection` and `redact` are regex heuristics. They catch common patterns and give
you trace signals; they are not complete defenses. Real protection comes from least
privilege (P3) and approvals (P4): an injected instruction can't do damage if the agent
lacks the permission.

## Repo layout

```
src/safe_agent_harness/   library (core, guards, sandbox, approvers, models, evals, cli)
docs/                     applying-the-skill.md
slides/                   safe-agent-harness.pptx
skills/safe-agent-harness/ SKILL.md + references/ (pointers, prompts)
commands/                 slash commands for Claude Code and Cursor
adapters/                 CLAUDE.md, Cursor rule, AGENTS.md snippets
examples/                 support_agent.py, eval_suite.py
tests/                    pytest suite
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: use a private GitHub advisory.

## License

MIT
