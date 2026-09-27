"""safe-agent-harness: a safe, secure, observable harness for LLM agents.

Agent = Model + Harness. The model proposes; the harness decides.
"""

from .approvers import allow_all, cli_approver, deny_all, policy_approver
from .core import (KILL_SWITCH_ENV, Budget, BudgetExceeded, FailureLog, Harness,
                   MemorySink, Risk, RateLimiter, SessionMemory, Tool, ToolRegistry,
                   Tracer, TransientError, call_with_retry, tool)
from .evals import EvalCase, EvalReport, run_evals
from .guards import (OutputRejected, OutputValidator, redact, scan_injection,
                     wrap_tool_output)
from .models import AnthropicClient, FakeModel
from .sandbox import run_in_sandbox

__version__ = "0.1.0"

__all__ = [
    "Harness", "Tool", "ToolRegistry", "tool", "Risk",
    "Budget", "BudgetExceeded", "RateLimiter", "KILL_SWITCH_ENV",
    "SessionMemory", "Tracer", "MemorySink", "FailureLog",
    "TransientError", "call_with_retry",
    "run_in_sandbox",
    "deny_all", "allow_all", "cli_approver", "policy_approver",
    "OutputValidator", "OutputRejected", "redact", "scan_injection", "wrap_tool_output",
    "AnthropicClient", "FakeModel",
    "EvalCase", "EvalReport", "run_evals",
    "__version__",
]
