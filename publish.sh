#!/usr/bin/env bash
# One-shot publish: fills placeholders, runs tests, creates a PUBLIC GitHub repo, pushes.
# Requires: git, python 3.10+, GitHub CLI (gh) logged in via `gh auth login`.
set -euo pipefail

REPO_NAME="${1:-safe-agent-harness}"

command -v gh >/dev/null || { echo "Install GitHub CLI: https://cli.github.com"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login"; exit 1; }

GH_USER="$(gh api user --jq .login)"
GH_NAME="$(gh api user --jq '.name // .login')"
echo "Publishing as $GH_USER ($GH_NAME) -> github.com/$GH_USER/$REPO_NAME (public)"

# Fill placeholders (works on macOS and Linux sed)
for f in pyproject.toml README.md LICENSE; do
  sed -i.bak "s/YOUR_USERNAME/$GH_USER/g; s/YOUR NAME/$GH_NAME/g; s/Your Name/$GH_NAME/g" "$f" && rm -f "$f.bak"
done

# Test before publishing
python3 -m venv .venv && . .venv/bin/activate
pip install -q -e ".[dev]"
pytest -q
(cd examples && python eval_suite.py > /dev/null) && echo "evals: pass"
deactivate

# Commit and push
git init -q -b main
git add .
git commit -q -m "Initial release v0.1.0: safe-agent-harness library, skill, and commands"
gh repo create "$REPO_NAME" --public --source=. --remote=origin --push \
  --description "Build LLM agents that can't quietly do damage: risk-tiered tools, approvals, sandboxing, limits, guards, tracing, evals."
gh repo edit "$GH_USER/$REPO_NAME" --add-topic llm,ai-agents,ai-safety,tool-calling,guardrails,claude,prompt-injection,mcp

echo "Done: https://github.com/$GH_USER/$REPO_NAME"
