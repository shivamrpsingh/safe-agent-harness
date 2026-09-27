---
description: Scaffold a new safe agent with safe-agent-harness
---
Use the safe-agent-harness skill (skills/safe-agent-harness/SKILL.md).

Scaffold a new agent for: $ARGUMENTS

Follow the SKILL.md build order. Ask me for the purpose, never-do list, and tools
if they aren't given. Use @tool with strict Pydantic args and a risk tier on each tool,
a policy_approver for irreversible tools, Budget limits, OutputValidator, and a
FakeModel-based test. End with the exit checklist.
