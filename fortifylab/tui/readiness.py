"""Initial setup and readiness workflow contract for the Python TUI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from fortifylab.config import EnvDocument, validate_env_file
from fortifylab.config.schema import redacted_value
from fortifylab.diagnostics import CheckStatus, DoctorReport, build_clone_safe_doctor_report, redact_diagnostic_text
from fortifylab.paths import repo_root
from fortifylab.status import LabStatus, build_check_status
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


class ReadinessState(str, Enum):
    """High-level setup readiness states rendered by the TUI."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class ReadinessSignal:
    """One non-mutating readiness signal for the setup overview."""

    id: str
    label: str
    state: ReadinessState
    summary: str
    detail: str = ""
    source: str = ""


@dataclass(frozen=True)
class RecommendedAction:
    """A handoff from readiness into an existing workflow target."""

    key: str
    label: str
    workflow_target: str
    summary: str


@dataclass(frozen=True)
class ReadinessSnapshot:
    """Complete read-only readiness overview for the initial setup screen."""

    signals: tuple[ReadinessSignal, ...]
    actions: tuple[RecommendedAction, ...]

    @property
    def state(self) -> ReadinessState:
        states = {signal.state for signal in self.signals}
        if ReadinessState.FAIL in states:
            return ReadinessState.FAIL
        if ReadinessState.WARN in states:
            return ReadinessState.WARN
        if states and states <= {ReadinessState.SKIP}:
            return ReadinessState.SKIP
        return ReadinessState.PASS


DoctorReportProvider = Callable[[], DoctorReport]
StatusProvider = Callable[[], LabStatus]
SnapshotProvider = Callable[[], ReadinessSnapshot]


DEFAULT_RECOMMENDED_ACTIONS: tuple[RecommendedAction, ...] = (
    RecommendedAction("1", "Open Configuration Editor", "configuration_editor", "Review .env diagnostics, validation, and derived URL repair previews."),
    RecommendedAction("2", "Open Doctor", "doctor", "Inspect clone-safe prerequisite, license, cluster, registry, and TLS checks."),
    RecommendedAction("3", "Open Status", "status", "Review the deterministic lab status summary or injected live-lab status."),
    RecommendedAction("4", "Open Help Center", "help_center", "Read setup, troubleshooting, and FortifyLab workflow guidance."),
    RecommendedAction("5", "Open Lifecycle Controls", "lifecycle", "Start, stop, or destroy supported lab components after readiness review."),
    RecommendedAction("6", "Open Logs", "logs", "Inspect available redacted wizard and application log sources."),
)


def build_setup_readiness_snapshot(
    *,
    env_file: Path | str | None = None,
    doctor_report_provider: DoctorReportProvider | None = None,
    status_provider: StatusProvider | None = None,
) -> ReadinessSnapshot:
    """Build a clone-safe setup readiness snapshot from existing domain APIs."""

    env_path = Path(env_file) if env_file is not None else repo_root() / ".env"
    doctor_report = (doctor_report_provider or build_clone_safe_doctor_report)()
    status = (status_provider or build_check_status)()
    signals = (
        _config_signal(env_path),
        _license_signal(env_path),
        _prerequisite_signal(doctor_report),
        _live_lab_signal(status),
    )
    return ReadinessSnapshot(signals, DEFAULT_RECOMMENDED_ACTIONS)


@dataclass
class SetupReadinessScreen(WorkflowScreen):
    """Pure TUI model for the Initial setup and readiness menu path."""

    def __init__(
        self,
        *,
        snapshot_provider: SnapshotProvider | None = None,
        env_file: Path | str | None = None,
        doctor_report_provider: DoctorReportProvider | None = None,
        status_provider: StatusProvider | None = None,
    ) -> None:
        super().__init__(
            "setup_readiness",
            "Initial setup and readiness",
            "Read-only setup overview: configuration, license, prerequisites, live-lab status, and workflow handoffs.",
        )
        self._snapshot_provider = snapshot_provider or (
            lambda: build_setup_readiness_snapshot(
                env_file=env_file,
                doctor_report_provider=doctor_report_provider,
                status_provider=status_provider,
            )
        )
        self._snapshot = self._snapshot_provider()
        self.selected_action_index = 0
        self.last_handoff: RecommendedAction | None = None

    @property
    def snapshot(self) -> ReadinessSnapshot:
        return self._snapshot

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def refresh(self) -> str:
        self._snapshot = self._snapshot_provider()
        self.selected_action_index = min(self.selected_action_index, max(len(self._snapshot.actions) - 1, 0))
        self.last_handoff = None
        return self.render()

    def render(self) -> str:
        lines = [self.summary, f"Overall readiness: {self._snapshot.state.value}", "", "Signals:"]
        for signal in self._snapshot.signals:
            detail = f" - {signal.detail}" if signal.detail else ""
            source = f" ({signal.source})" if signal.source else ""
            lines.append(redact_diagnostic_text(f"{signal.state.value:<4} {signal.label}: {signal.summary}{detail}{source}"))
        lines.extend(("", "Recommended actions:"))
        for index, action in enumerate(self._snapshot.actions):
            marker = ">" if index == self.selected_action_index else " "
            lines.append(f"{marker} {action.key}  {action.label} -> {action.workflow_target}: {action.summary}")
        lines.extend(("", "Actions:", "up/down  Select action", "1-6  Jump to action", "enter/o  Handoff to selected workflow", "r  Refresh", "b  Back to menu", "q  Quit"))
        if self.last_handoff is not None:
            lines.extend(("", f"Selected handoff: {self.last_handoff.workflow_target}"))
        return "\n".join(lines)

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"r", "refresh"}:
            self.refresh()
            return WorkflowKeyResult("Refreshed setup readiness.")
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        if key in {"up", "k"}:
            self._move(-1)
            return WorkflowKeyResult("Selected previous readiness action.")
        if key in {"down", "j"}:
            self._move(1)
            return WorkflowKeyResult("Selected next readiness action.")
        if key.isdigit():
            return self._select_number(key)
        if key in {"enter", "o"}:
            return self._handoff_selected()
        return WorkflowKeyResult(f"No setup readiness workflow action is bound to {key!r}.")

    on_key = handle_key

    def _move(self, offset: int) -> None:
        if not self._snapshot.actions:
            self.selected_action_index = 0
            return
        self.selected_action_index = (self.selected_action_index + offset) % len(self._snapshot.actions)

    def _select_number(self, key: str) -> WorkflowKeyResult:
        for index, action in enumerate(self._snapshot.actions):
            if action.key == key:
                self.selected_action_index = index
                return WorkflowKeyResult(f"Selected readiness action {key}: {action.label}.")
        return WorkflowKeyResult(f"No readiness action is bound to {key!r}.")

    def _handoff_selected(self) -> WorkflowKeyResult:
        if not self._snapshot.actions:
            return WorkflowKeyResult("No readiness handoff is available.")
        action = self._snapshot.actions[self.selected_action_index]
        self.last_handoff = action
        return WorkflowKeyResult(f"Open workflow target: {action.workflow_target}.", open_target=action.workflow_target)


def build_setup_readiness_workflow(
    *,
    snapshot_provider: SnapshotProvider | None = None,
    env_file: Path | str | None = None,
    doctor_report_provider: DoctorReportProvider | None = None,
    status_provider: StatusProvider | None = None,
) -> SetupReadinessScreen:
    return SetupReadinessScreen(
        snapshot_provider=snapshot_provider,
        env_file=env_file,
        doctor_report_provider=doctor_report_provider,
        status_provider=status_provider,
    )


def _config_signal(env_path: Path) -> ReadinessSignal:
    if not env_path.is_file():
        return ReadinessSignal(
            "config",
            "Configuration",
            ReadinessState.WARN,
            ".env is unavailable",
            "open Configuration Editor to validate or create local configuration",
            "fortifylab.config",
        )
    try:
        issues = validate_env_file(env_path)
    except OSError as exc:
        return ReadinessSignal("config", "Configuration", ReadinessState.SKIP, "configuration could not be read", str(exc), "fortifylab.config")
    if issues:
        return ReadinessSignal(
            "config",
            "Configuration",
            ReadinessState.FAIL,
            f"{len(issues)} validation finding(s)",
            "open Configuration Editor for redacted details",
            "fortifylab.config",
        )
    return ReadinessSignal("config", "Configuration", ReadinessState.PASS, ".env validation passed", source="fortifylab.config")


def _license_signal(env_path: Path) -> ReadinessSignal:
    if not env_path.is_file():
        return ReadinessSignal("license", "License", ReadinessState.SKIP, "license path unavailable until .env exists", source="fortifylab.config")
    try:
        document = EnvDocument.read(env_path)
    except OSError as exc:
        return ReadinessSignal("license", "License", ReadinessState.SKIP, "license path could not be read", str(exc), "fortifylab.config")
    license_path = document.get("FORTIFY_LICENSE_FILE")
    if not license_path:
        return ReadinessSignal("license", "License", ReadinessState.WARN, "FORTIFY_LICENSE_FILE is unset", source="fortifylab.config")
    if Path(license_path).expanduser().is_file():
        return ReadinessSignal("license", "License", ReadinessState.PASS, "license file path is present", redacted_value("FORTIFY_LICENSE_FILE", license_path), "fortifylab.config")
    return ReadinessSignal(
        "license",
        "License",
        ReadinessState.WARN,
        "license file is not available from this clone-safe check",
        redacted_value("FORTIFY_LICENSE_FILE", license_path),
        "fortifylab.config",
    )


def _prerequisite_signal(report: DoctorReport) -> ReadinessSignal:
    results = tuple(result for section in report.sections for result in section.results if section.name in {"prerequisites", "license", "registry", "tls"})
    if not results:
        return ReadinessSignal("prerequisites", "Prerequisites", ReadinessState.SKIP, "doctor report has no prerequisite signals", source="fortifylab.diagnostics")
    states = tuple(result.status for result in results)
    if CheckStatus.FAIL in states:
        state = ReadinessState.FAIL
    elif CheckStatus.WARN in states:
        state = ReadinessState.WARN
    elif all(status is CheckStatus.SKIP for status in states):
        state = ReadinessState.SKIP
    else:
        state = ReadinessState.PASS
    counts = " | ".join(f"{status.value} {states.count(status)}" for status in CheckStatus)
    return ReadinessSignal("prerequisites", "Prerequisites", state, "doctor checks aggregated", counts, "fortifylab.diagnostics")


def _live_lab_signal(status: LabStatus) -> ReadinessSignal:
    if status.cluster == "clone-safe":
        return ReadinessSignal("live_lab", "Live lab", ReadinessState.SKIP, "live Kubernetes/network checks deferred", status.summary, "fortifylab.status")
    if not status.components:
        return ReadinessSignal("live_lab", "Live lab", ReadinessState.SKIP, "no live lab components reported", source="fortifylab.status")
    state = ReadinessState.PASS if status.ok else ReadinessState.WARN
    detail = status.summary
    if status.warnings:
        detail = f"{detail}; {len(status.warnings)} warning(s)"
    return ReadinessSignal("live_lab", "Live lab", state, "status provider reported lab state", detail, "fortifylab.status")


@dataclass
class ResetTiersScreen(WorkflowScreen):
    """Read-only reset guidance that hands off to lifecycle controls."""

    def __init__(self) -> None:
        super().__init__(
            "setup_readiness.reset_tiers",
            "Complete lab reset tiers",
            "Read-only reset guidance: review lifecycle controls before any destructive reset operation.",
        )
        self.last_handoff: RecommendedAction | None = None

    def render(self) -> str:
        return "\n".join(
            (
                self.summary,
                "SKIP Lab reset: no Kubernetes, Helm, Docker, network, or filesystem mutation is performed here.",
                "",
                "Actions:",
                "enter/o  Open Lifecycle Controls",
                "b  Back to menu",
                "q  Quit",
            )
        )

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"enter", "o"}:
            self.last_handoff = RecommendedAction("5", "Open Lifecycle Controls", "lifecycle", "Review lifecycle reset/stop/start options.")
            return WorkflowKeyResult("Open workflow target: lifecycle.", open_target="lifecycle")
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        return WorkflowKeyResult(f"No reset tiers workflow action is bound to {key!r}.")


def build_reset_tiers_workflow() -> ResetTiersScreen:
    return ResetTiersScreen()
