# Contributing

1. `pip install -e ".[dev]"` and `pytest -q` before opening a PR.
2. New features map to a pointer (P1–P10). Update `skills/safe-agent-harness/references/pointers.md`
   and add a test.
3. Security issues: open a private advisory on GitHub, not a public issue.
4. Keep the core dependency-free beyond Pydantic. Provider SDKs go in optional extras.
