"""P4 approvers for irreversible actions. Every approver fails closed."""

from __future__ import annotations

from typing import Callable

Approver = Callable[[str, dict], bool]


def deny_all(tool: str, args: dict) -> bool:
    """Default. Nothing irreversible ever runs."""
    return False


def allow_all(tool: str, args: dict) -> bool:
    """Tests and local development only. Never use in production."""
    return True


def cli_approver(tool: str, args: dict) -> bool:
    """Ask in the terminal. Anything but 'y' denies."""
    try:
        answer = input(f"\nApprove {tool}({args})? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def policy_approver(rules: dict[str, Callable[[dict], bool]],
                    escalate: Approver = deny_all) -> Approver:
    """Auto-approve when a per-tool rule passes, otherwise escalate.

    Example: policy_approver({"refund": lambda a: a["amount"] <= 50}, escalate=cli_approver)
    """
    def approve(tool: str, args: dict) -> bool:
        rule = rules.get(tool)
        try:
            if rule and rule(args):
                return True
        except Exception:  # noqa: BLE001 - a broken rule escalates, never approves
            pass
        return escalate(tool, args)
    return approve
