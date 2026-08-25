"""Clone-safe doctor report helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import os

from .baseline import default_checks
from .models import (
    CheckStatus,
    DiagnosticCheck,
    DiagnosticCommandResult,
    DiagnosticResult,
    DiagnosticSection,
    DiagnosticSeverity,
    DoctorReport,
)
from .redaction import redact_diagnostic_text

Executor = Callable[[tuple[str, ...]], DiagnosticCommandResult]


class DiagnosticRunner:
    def __init__(self, *, checks: Iterable[DiagnosticCheck], executor: Executor | None = None) -> None:
        self.checks = tuple(checks)
        self.executor = executor

    def run_all(self) -> tuple[DiagnosticResult, ...]:
        results: list[DiagnosticResult] = []
        for check in self.checks:
            if check.command and self.executor is not None:
                command_result = self.executor(check.command)
                status = CheckStatus.PASS if command_result.ok else CheckStatus.FAIL
                detail = "\n".join(part for part in (command_result.stdout, command_result.stderr) if part)
                results.append(
                    DiagnosticResult(
                        check_id=check.id,
                        status=status,
                        severity=check.severity,
                        summary=check.label,
                        detail=redact_diagnostic_text(detail),
                        duration_seconds=command_result.duration_seconds,
                    )
                )
            else:
                results.append(
                    DiagnosticResult(
                        check_id=check.id,
                        status=CheckStatus.PASS,
                        severity=check.severity,
                        summary=check.label,
                    )
                )
        return tuple(results)


def build_clone_safe_doctor_report(*, scenario: str = "ok") -> DoctorReport:
    checks = default_checks()
    results: list[DiagnosticResult] = []
    for check in checks:
        status = CheckStatus.PASS
        severity = check.severity
        detail = "clone-safe read-only check"
        if check.command:
            status = CheckStatus.SKIP
            detail = "deferred: requires live lab environment"
        if scenario == "warning" and check.category == "cluster":
            status = CheckStatus.WARN
            severity = DiagnosticSeverity.WARN
            detail = "test warning fixture"
        results.append(DiagnosticResult(check.id, status, severity, check.label, detail))

    sections: list[DiagnosticSection] = []
    for category in ("prerequisites", "license", "cluster", "pods", "registry", "tls"):
        sections.append(DiagnosticSection(category, tuple(result for result in results if result.check_id.startswith(category) or _category_for(result.check_id) == category)))
    return DoctorReport("FortifyLab Doctor", tuple(sections))


def _category_for(check_id: str) -> str:
    return {check.id: check.category for check in default_checks()}.get(check_id, "prerequisites")


def render_doctor_report(report: DoctorReport) -> str:
    lines = [report.title]
    extra = tuple(value for key, value in os.environ.items() if key.startswith("FORTIFYLAB_TEST_SECRET") and value)
    for section in report.sections:
        lines.append(f"[{section.name}]")
        for result in section.results:
            detail = f" - {result.detail}" if result.detail else ""
            lines.append(redact_diagnostic_text(f"{result.status.value} {result.check_id}: {result.summary}{detail}", extra_values=extra))
    return "\n".join(lines) + "\n"


def doctor_command(*, check: bool = False, strict: bool = False, scenario: str = "ok", print_line: Callable[[str], None] = print) -> int:
    report = build_clone_safe_doctor_report(scenario=scenario)
    for line in render_doctor_report(report).rstrip().splitlines():
        print_line(line)
    if strict and report.has_warnings_or_failures:
        return 1
    return 0
