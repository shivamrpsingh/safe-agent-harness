---
description: Add a risk-tiered, validated tool to an agent
---
Use the safe-agent-harness skill, routes P3, P4, P5.

Add this tool: $ARGUMENTS

Decide the risk tier with the "can it be undone without contacting anyone" rule and say why.
Constrain every argument in the Pydantic model. Set untrusted_output=True if it returns
external content. Add one normal and one adversarial EvalCase. End with the exit checklist.
