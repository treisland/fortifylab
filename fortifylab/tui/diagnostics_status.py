"""Doctor and status workflow screens for the Python TUI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fortifylab.diagnostics import (
    CheckStatus,
    DoctorReport,
    build_clone_safe_doctor_report,
    redact_diagnostic_text,
    render_doctor_report,
)
from fortifylab.status import LabStatus, build_check_status, render_status
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


DoctorReportProvider = Callable[[], DoctorReport]
StatusProvider = Callable[[], LabStatus]


@dataclass
class DoctorScreen(WorkflowScreen):
    """Pure TUI model for clone-safe doctor results."""

    def __init__(self, doctor_report_provider: DoctorReportProvider | None = None, *, screen_id: str = "doctor", title: str = "FortifyLab Doctor") -> None:
        super().__init__(
            screen_id,
            title,
            "Clone-safe diagnostics: live lab checks are skipped unless a diagnostics API enables them.",
        )
        self._doctor_report_provider = doctor_report_provider or build_clone_safe_doctor_report
        self._report = self._doctor_report_provider()

    def refresh(self) -> str:
        self._report = self._doctor_report_provider()
        return self.render()

    def render(self) -> str:
        return self.render_doctor()

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def render_doctor(self) -> str:
        counts = {status: 0 for status in CheckStatus}
        for section in self._report.sections:
            for result in section.results:
                counts[result.status] += 1

        lines = [
            self.summary,
            "Result states: PASS ready, WARN attention, FAIL blocked, SKIP clone-safe deferred.",
            (
                "Summary: "
                f"PASS {counts[CheckStatus.PASS]} | "
                f"WARN {counts[CheckStatus.WARN]} | "
                f"FAIL {counts[CheckStatus.FAIL]} | "
                f"SKIP {counts[CheckStatus.SKIP]}"
            ),
            "",
        ]
        for section in self._report.sections:
            if not section.results:
                continue
            lines.append(f"[{section.name}]")
            for result in section.results:
                detail = f" - {result.detail}" if result.detail else ""
                lines.append(redact_diagnostic_text(f"{result.status.value:<4} {result.check_id}: {result.summary}{detail}"))
            lines.append("")
        lines.extend(("Redacted output:", _bounded_output(render_doctor_report(self._report).rstrip()), "", *self._actions()))
        return "\n".join(lines).rstrip()

    doctor = render_doctor
    doctor_panel = render_doctor

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key == "r":
            self.refresh()
            return WorkflowKeyResult("Refreshed doctor diagnostics.")
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        return WorkflowKeyResult(f"No doctor workflow action is bound to {key!r}.")

    on_key = handle_key

    def _actions(self) -> tuple[str, ...]:
        return ("Actions:", "r  Refresh", "b  Back to menu", "q  Quit")


@dataclass
class StatusScreen(WorkflowScreen):
    """Pure TUI model for clone-safe lab status results."""

    def __init__(self, status_provider: StatusProvider | None = None, *, screen_id: str = "status", title: str = "FortifyLab Status") -> None:
        super().__init__(
            screen_id,
            title,
            "Clone-safe status: deterministic summary only; live Kubernetes and network checks stay deferred.",
        )
        self._status_provider = status_provider or build_check_status
        self._status = self._status_provider()

    def refresh(self) -> str:
        self._status = self._status_provider()
        return self.render()

    def render(self) -> str:
        return self.render_status()

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def render_status(self) -> str:
        lines = [
            self.summary,
            f"Cluster: {redact_diagnostic_text(self._status.cluster)}",
            f"Namespace: {redact_diagnostic_text(self._status.namespace)}",
            f"Components: {self._status.summary}",
            "",
            "[components]",
        ]
        for component in self._status.components:
            state = "PASS" if component.ok else "FAIL"
            detail = f" - {component.message}" if component.message else ""
            lines.append(redact_diagnostic_text(f"{state:<4} {component.name}: {component.ready}/{component.desired} {component.status}{detail}"))
        if self._status.warnings:
            lines.append("")
            lines.append("[warnings]")
            for warning in self._status.warnings:
                lines.append(redact_diagnostic_text(f"WARN {warning}"))
        if not self._status.components and not self._status.warnings:
            lines.append("SKIP no status components are available in clone-safe mode")
        lines.extend(("", "Redacted output:", _bounded_output(redact_diagnostic_text(render_status(self._status).rstrip())), "", *self._actions()))
        return "\n".join(lines).rstrip()

    status = render_status
    status_panel = render_status

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key == "r":
            self.refresh()
            return WorkflowKeyResult("Refreshed lab status.")
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        return WorkflowKeyResult(f"No status workflow action is bound to {key!r}.")

    on_key = handle_key

    def _actions(self) -> tuple[str, ...]:
        return ("Actions:", "r  Refresh", "b  Back to menu", "q  Quit")


@dataclass
class DiagnosticsScreen(WorkflowScreen):
    """Combined diagnostics/status dashboard for the Diagnostics menu path."""

    def __init__(self, doctor_report_provider: DoctorReportProvider | None = None, status_provider: StatusProvider | None = None) -> None:
        super().__init__(
            "diagnostics",
            "Diagnostics",
            "Clone-safe Doctor and Status results. Refresh re-runs deterministic M5 report/status builders.",
        )
        self._doctor = DoctorScreen(doctor_report_provider=doctor_report_provider)
        self._status = StatusScreen(status_provider=status_provider)

    def refresh(self) -> str:
        self._doctor.refresh()
        self._status.refresh()
        return self.render()

    def render(self) -> str:
        return "\n\n".join((self.summary, "Doctor", self.render_doctor(), "Status", self.render_status(), "Actions:\nr  Refresh\nb  Back to menu\nq  Quit"))

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def render_doctor(self) -> str:
        return self._doctor.render_doctor()

    doctor = render_doctor
    doctor_panel = render_doctor

    def render_status(self) -> str:
        return self._status.render_status()

    status = render_status
    status_panel = render_status

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key == "r":
            self.refresh()
            return WorkflowKeyResult("Refreshed diagnostics and status.")
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        return WorkflowKeyResult(f"No diagnostics workflow action is bound to {key!r}.")

    on_key = handle_key


DoctorWorkflowScreen = DoctorScreen
StatusWorkflowScreen = StatusScreen


def build_diagnostics_workflow(
    doctor_report_provider: DoctorReportProvider | None = None,
    status_provider: StatusProvider | None = None,
) -> DiagnosticsScreen:
    return DiagnosticsScreen(doctor_report_provider=doctor_report_provider, status_provider=status_provider)


def build_doctor_workflow(doctor_report_provider: DoctorReportProvider | None = None) -> DoctorScreen:
    return DoctorScreen(doctor_report_provider=doctor_report_provider)


def build_status_workflow(status_provider: StatusProvider | None = None) -> StatusScreen:
    return StatusScreen(status_provider=status_provider)


def _bounded_output(text: str, *, limit: int = 80) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    hidden = len(lines) - limit
    return "\n".join([*lines[:limit], f"... {hidden} more lines"])
