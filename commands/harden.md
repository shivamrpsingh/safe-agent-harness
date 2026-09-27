---
description: Harden an existing agent against injection, runaway cost, and data leaks
---
Use the safe-agent-harness skill, routes P5, P6, P7, P8.

Harden: $ARGUMENTS

Mark external-content tools untrusted, move code execution into run_in_sandbox with Docker,
set Budget and RateLimiter values, and add an OutputValidator. Show a diff and end with the
exit checklist.
