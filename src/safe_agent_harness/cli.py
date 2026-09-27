"""`safe-agent-harness init` - install the skill, commands, and rules into a repo.

    uvx safe-agent-harness init            # interactive
    uvx safe-agent-harness init --all      # Claude Code + Cursor + AGENTS.md
    uvx safe-agent-harness init --claude --cursor
"""
from __future__ import annotations

import argparse
import shutil
import sys
from importlib.resources import files
from pathlib import Path

def _bundle():
    """Wheel installs ship files under _bundle; source checkouts use the repo folders."""
    b = files("safe_agent_harness") / "_bundle"
    if b.is_dir():
        return {"skill": b / "skill", "commands": b / "commands", "adapters": b / "adapters"}
    repo = Path(__file__).resolve().parents[2]
    return {"skill": repo / "skills" / "safe-agent-harness",
            "commands": repo / "commands", "adapters": repo / "adapters"}
MARK = "<!-- safe-agent-harness -->"


def _copy_tree(src, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree(item, target)
        else:
            target.write_bytes(item.read_bytes())


def _append_once(path: Path, text: str) -> str:
    existing = path.read_text() if path.exists() else ""
    if MARK in existing:
        return "already present"
    path.write_text(existing + ("\n\n" if existing else "") + f"{MARK}\n{text}")
    return "updated" if existing else "created"


def install(root: Path, claude: bool, cursor: bool, agents: bool) -> list[str]:
    done = []
    B = _bundle()
    adapters = B["adapters"]
    if cursor or agents:
        _copy_tree(B["skill"], root / "skills" / "safe-agent-harness")
        done.append("skills/safe-agent-harness/")
    if claude:
        _copy_tree(B["skill"], root / ".claude" / "skills" / "safe-agent-harness")
        _copy_tree(B["commands"], root / ".claude" / "commands")
        r = _append_once(root / "CLAUDE.md", (adapters / "CLAUDE.md.snippet").read_text())
        done += [".claude/skills/safe-agent-harness/", ".claude/commands/ (7)", f"CLAUDE.md ({r})"]
    if cursor:
        rules = root / ".cursor" / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        (rules / "safe-agent-harness.mdc").write_text((adapters / "cursor-rule.mdc").read_text())
        _copy_tree(B["commands"], root / ".cursor" / "commands")
        done += [".cursor/rules/safe-agent-harness.mdc", ".cursor/commands/ (7)"]
    if agents:
        r = _append_once(root / "AGENTS.md", (adapters / "AGENTS.md.snippet").read_text())
        done.append(f"AGENTS.md ({r})")
    return done


def _ask(q: str) -> bool:
    try:
        return input(f"{q} [Y/n] ").strip().lower() in ("", "y", "yes")
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="safe-agent-harness")
    sub = p.add_subparsers(dest="cmd")
    i = sub.add_parser("init", help="install the skill into this repo")
    i.add_argument("--claude", action="store_true", help="Claude Code")
    i.add_argument("--cursor", action="store_true", help="Cursor")
    i.add_argument("--agents", action="store_true", help="AGENTS.md (Codex, Copilot, Windsurf, Gemini CLI)")
    i.add_argument("--all", action="store_true")
    i.add_argument("--path", default=".", help="repo root (default: current dir)")
    sub.add_parser("version")
    a = p.parse_args(argv)

    if a.cmd == "version":
        from . import __version__
        print(__version__)
        return 0
    if a.cmd != "init":
        p.print_help()
        return 1

    claude, cursor, agents = a.claude or a.all, a.cursor or a.all, a.agents or a.all
    if not (claude or cursor or agents):
        if not sys.stdin.isatty():
            print("No target given. Use --claude, --cursor, --agents, or --all.")
            return 1
        claude = _ask("Install for Claude Code?")
        cursor = _ask("Install for Cursor?")
        agents = _ask("Add to AGENTS.md (Codex, Copilot, Windsurf, Gemini CLI)?")

    root = Path(a.path).resolve()
    for line in install(root, claude, cursor, agents):
        print(f"  + {line}")
    print("\nDone. Try: /new-agent a support agent that looks up orders and issues refunds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
