"""safe-agent-harness: a safe, secure, observable harness for LLM agents.

Agent = Model + Harness. The model proposes; the harness decides.
"""

from .approvers import allow_all, cli_approver, deny_all, policy_approver
from .core import (KILL_SWITCH_ENV, Budget, BudgetExceeded, CostBudget, FailureLog, Harness,
                   MemorySink, Risk, RateLimiter, RunResult, SessionMemory, Tool, ToolRegistry,
                   Tracer, TransientError, call_with_retry, tool)
from .evals import EvalCase, EvalReport, run_evals
from .guards import (OutputRejected, OutputValidator, redact, scan_injection,
                     wrap_tool_output)
from .models import AnthropicClient, FakeModel, OllamaClient
from .sandbox import run_in_sandbox

__version__ = "0.2.0"

__all__ = [
    "Harness", "Tool", "ToolRegistry", "tool", "Risk",
    "Budget", "CostBudget", "BudgetExceeded", "RateLimiter", "KILL_SWITCH_ENV",
    "SessionMemory", "Tracer", "MemorySink", "FailureLog",
    "TransientError", "call_with_retry",
    "run_in_sandbox",
    "deny_all", "allow_all", "cli_approver", "policy_approver",
    "OutputValidator", "OutputRejected", "redact", "scan_injection", "wrap_tool_output",
    "AnthropicClient", "FakeModel", "OllamaClient",
    "RunResult",
    "EvalCase", "EvalReport", "run_evals",
    "__version__",
]
