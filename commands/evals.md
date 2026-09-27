---
description: Generate an eval suite with attack cases and a CI gate
---
Use the safe-agent-harness skill, route P10.

Build evals for: $ARGUMENTS

Write 30 EvalCases (18 normal, 6 edge, 6 adversarial covering injection, bad args,
budget exhaustion, and PII), using FakeModel scripts for harness behavior. Call
run_evals(threshold=0.95) and add a CI step that fails below it.
