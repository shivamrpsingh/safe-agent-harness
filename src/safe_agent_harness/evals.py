"""P10 evals: run scripted or live cases against a harness and gate on pass rate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .core import Harness, MemorySink, Tracer


@dataclass
class EvalCase:
    name: str
    task: str
    check: Callable[[str, MemorySink], bool]
    tags: list[str] = field(default_factory=list)  # e.g. ["adversarial", "injection"]
    model_script: list | None = None  # for FakeModel-driven harness tests


@dataclass
class EvalResult:
    name: str
    passed: bool
    answer: str
    tags: list[str]
    error: str | None = None


@dataclass
class EvalReport:
    results: list[EvalResult]

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results) if self.results else 0.0

    def failed(self) -> list[EvalResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        lines = [f"{'PASS' if r.passed else 'FAIL'}  {r.name}  {r.tags}" for r in self.results]
        lines.append(f"pass rate: {self.pass_rate:.0%} ({sum(r.passed for r in self.results)}/{len(self.results)})")
        return "\n".join(lines)


def run_evals(make_harness: Callable[[EvalCase, Tracer], Harness],
              cases: list[EvalCase], threshold: float | None = None) -> EvalReport:
    """make_harness(case, tracer) must return a fresh Harness wired to `tracer`.

    If threshold is set and the pass rate is below it, raises AssertionError
    (useful as a CI gate).
    """
    results = []
    for case in cases:
        sink = MemorySink()
        h = make_harness(case, Tracer(sink))
        try:
            answer = h.run("eval-user", f"eval-{case.name}", case.task)
            ok = bool(case.check(answer, sink))
            results.append(EvalResult(case.name, ok, answer, case.tags))
        except Exception as e:  # noqa: BLE001
            results.append(EvalResult(case.name, False, "", case.tags, error=str(e)))
    report = EvalReport(results)
    if threshold is not None and report.pass_rate < threshold:
        raise AssertionError(f"eval pass rate {report.pass_rate:.0%} below {threshold:.0%}\n"
                             + report.summary())
    return report
