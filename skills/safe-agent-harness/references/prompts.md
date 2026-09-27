# Developer prompts

Copy a prompt, fill the `<angle brackets>`, and paste it into Cursor, Claude Code, or any
AI coding tool that has this skill loaded. Each prompt names the pointers it triggers so the
assistant reads the right reference sections.

---

## 1. Start a new agent (P1, P2, P4)

```
Using the safe-agent-harness skill, scaffold a new agent.
Purpose: <one sentence>
Never do: <list>
Tools it needs: <tool: what it does>
Use the safe_agent_harness library. Tag each tool with a risk tier, add Pydantic
args models, and end with the exit checklist.
```

## 2. Add a tool (P3, P4, P5)

```
Using safe-agent-harness, add a tool named <name> that <does X> via <API/DB>.
Decide its risk tier using the "can it be undone" rule and explain why.
Use a scoped credential from env var <NAME>. Wrap its output as data (P5).
Add one normal and one adversarial eval case for it.
```

## 3. Gate an irreversible action (P4)

```
Using safe-agent-harness P4, make <tool> require human approval.
Implement the approver as <Slack button / web UI confirm / CLI prompt>.
Default to deny on timeout after <N> seconds. Add an idempotency key.
```

## 4. Protect against prompt injection (P5)

```
Using safe-agent-harness P5, harden this agent against prompt injection from
<web pages / uploaded files / emails / RAG results>. Delimit tool output as data,
confirm no content can change tool permissions, and write 5 injection eval cases.
```

## 5. Sandbox code execution (P6)

```
Using safe-agent-harness P6, route all code execution through safe_agent_harness.run_in_sandbox
with Docker. Needed packages: <list>. Network access: <none / allowlist of hosts>.
Show the Dockerfile for the sandbox image.
```

## 6. Set limits and a kill switch (P7)

```
Using safe-agent-harness P7, set Budget and RateLimiter values for this agent.
Expected task: ~<N> steps, ~<N> tokens, <N>s. Users: <N> per minute peak.
Move RateLimiter and SessionMemory to Redis. Show how to test the kill switch.
```

## 7. Validate outputs (P8)

```
Using safe-agent-harness P8, add output validation to Harness.run().
Output format: <schema or description>. Must redact: <PII types / secrets>.
On failure: retry once, then degrade().
```

## 8. Wire observability (P9)

```
Using safe-agent-harness P9, set the Tracer sink with <Langfuse /
LangSmith / OpenTelemetry>. Add alerts for cost spikes, tool failure rate over
<N>%, and approval denials. Keep secrets and raw PII out of traces.
```

## 9. Build the eval suite (P10)

```
Using safe-agent-harness P10, create an eval suite for this agent with
30 cases: 18 normal, 6 edge, 6 adversarial (injection, out-of-scope, budget
exhaustion). Use EvalCase, run_evals, and FakeModel. Add a CI job that
blocks merge below <N>% pass rate.
```

## 10. Review a PR (all)

```
Using safe-agent-harness, review this diff against the P-all review checklist
in references/pointers.md. List blocking issues first, then non-blocking,
each with the file, line, pointer number, and a concrete fix.
```

## 11. Debug an agent run (P9, P1)

```
Using safe-agent-harness P9, here is the trace for run <trace_id>:
<paste JSON events>
Explain what happened step by step, identify the root cause, and propose a
code-level harness rule (not a prompt change) that prevents it.
```

## 12. Audit an existing agent (all)

```
Using safe-agent-harness, audit <path/to/agent>. Score each of the 10 pointers
as done, partial, or missing, with evidence from the code. Then give a
prioritized fix list in the build-workflow order from SKILL.md.
```
