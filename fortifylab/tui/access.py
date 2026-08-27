"""Dashboard access, URLs, and credential snapshot contracts for the TUI."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from fortifylab.config import EnvDocument
from fortifylab.config.schema import field_by_key, fields_for_section, redacted_value
from fortifylab.diagnostics import redact_diagnostic_text
from fortifylab.paths import repo_root
from fortifylab.status import LabStatus
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


class AccessEntryState(str, Enum):
    """High-level state for a read-only access item."""

    PASS = "PASS"
    PRESENT = "PASS"
    WARN = "WARN"
    MISSING = "WARN"
    SKIP = "SKIP"


AccessState = AccessEntryState


class ValueVisibility(str, Enum):
    """How a value is intentionally rendered by default."""

    VISIBLE = "VISIBLE"
    MASKED = "MASKED"
    UNSET = "UNSET"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AccessUrlEntry:
    """One URL or host shown by the dashboard/access workflow."""

    key: str
    label: str
    value: str
    state: AccessEntryState
    visibility: ValueVisibility = ValueVisibility.VISIBLE
    source: str = "fortifylab.config"
    detail: str = ""

    @property
    def id(self) -> str:
        return _entry_id(self.key)

    @property
    def url(self) -> str:
        return self.value

    @property
    def rendered_value(self) -> str:
        return self.value


@dataclass(frozen=True)
class CredentialEntry:
    """One credential-adjacent value, masked unless explicitly non-secret."""

    key: str
    label: str
    value: str
    state: AccessEntryState
    visibility: ValueVisibility
    source: str = "fortifylab.config"
    detail: str = ""
    reveal_supported: bool = False

    @property
    def id(self) -> str:
        return _entry_id(self.key)

    @property
    def rendered_value(self) -> str:
        return self.value


@dataclass(frozen=True)
class AccessHandoff:
    """A read-only handoff to an existing workflow target."""

    key: str
    label: str
    workflow_target: str
    summary: str


@dataclass(frozen=True)
class AccessSnapshot:
    """Read-only dashboard, URL, and credential overview for the TUI."""

    urls: tuple[AccessUrlEntry, ...]
    credentials: tuple[CredentialEntry, ...]
    handoffs: tuple[AccessHandoff, ...]
    notices: tuple[str, ...] = ()

    @property
    def has_missing_values(self) -> bool:
        return any(entry.state == AccessEntryState.MISSING for entry in (*self.urls, *self.credentials))


EnvValuesProvider = Callable[[], Mapping[str, str]]
AccessSnapshotProvider = Callable[[], AccessSnapshot]


URL_FIELDS: tuple[tuple[str, str], ...] = (
    ("dashboard", "Kubernetes Dashboard"),
    ("SSC_URL", "Software Security Center"),
    ("LIM_URL", "License and Infrastructure Manager"),
    ("LIM_API_URL", "LIM API"),
    ("SCDAST_URL", "ScanCentral DAST"),
    ("SCSAST_URL", "ScanCentral SAST"),
    ("SCSAST_CTRL_URL", "ScanCentral SAST Controller"),
    ("JUICE_SHOP_URL", "Juice Shop sample"),
    ("WEBGOAT_URL", "WebGoat sample"),
    ("DVWA_URL", "DVWA sample"),
)


DASHBOARD_TOKEN_ENTRIES: tuple[CredentialEntry, ...] = (
    CredentialEntry(
        "dashboard.viewer.token",
        "Dashboard viewer token",
        "<unavailable>",
        AccessEntryState.SKIP,
        ValueVisibility.UNAVAILABLE,
        "kubernetes-dashboard",
        "short-lived token generation is an explicit later workflow and is not run by this read-only screen",
        reveal_supported=False,
    ),
    CredentialEntry(
        "dashboard.admin.token",
        "Dashboard admin token",
        "<unavailable>",
        AccessEntryState.SKIP,
        ValueVisibility.UNAVAILABLE,
        "kubernetes-dashboard",
        "admin token generation remains gated outside clone-safe access rendering",
        reveal_supported=False,
    ),
)


DEFAULT_ACCESS_HANDOFFS: tuple[AccessHandoff, ...] = (
    AccessHandoff("1", "Open Configuration Editor", "configuration_editor", "Review or repair domain, URL, and credential settings."),
    AccessHandoff("2", "Open Status", "status", "Check whether the lab components are available before opening URLs."),
    AccessHandoff("3", "Open Diagnostics", "diagnostics", "Review clone-safe prerequisite, access, and status diagnostics."),
    AccessHandoff("4", "Open Help Center", "help_center", "Read dashboard, URL, TLS, and credential guidance."),
    AccessHandoff("5", "Open Logs", "logs", "Inspect redacted wizard and application logs."),
)


def build_access_snapshot(
    *,
    env_file: Path | str | None = None,
    env_values_provider: EnvValuesProvider | None = None,
    config_provider: EnvValuesProvider | None = None,
    status_provider: StatusProvider | None = None,
) -> AccessSnapshot:
    """Build a clone-safe access snapshot without touching live lab services."""

    values, notices = _load_values(env_file=env_file, env_values_provider=env_values_provider or config_provider)
    status_by_id, status_notices = _load_status(status_provider)
    notices.extend(status_notices)
    urls = tuple(_url_entry(key, label, values, status_by_id) for key, label in URL_FIELDS)
    credentials = tuple(_credential_entry(field.key, values) for field in fields_for_section("credentials")) + DASHBOARD_TOKEN_ENTRIES
    return AccessSnapshot(urls, credentials, DEFAULT_ACCESS_HANDOFFS, tuple(notices))


@dataclass
class AccessWorkflowScreen(WorkflowScreen):
    """Shared read-only screen model for dashboard access and URL/credential paths."""

    def __init__(
        self,
        *,
        screen_id: str,
        title: str,
        summary: str,
        snapshot_provider: AccessSnapshotProvider | None = None,
        env_file: Path | str | None = None,
        env_values_provider: EnvValuesProvider | None = None,
        config_provider: EnvValuesProvider | None = None,
        status_provider: StatusProvider | None = None,
    ) -> None:
        super().__init__(screen_id, title, summary)
        self._snapshot_provider = snapshot_provider or (
            lambda: build_access_snapshot(
                env_file=env_file,
                env_values_provider=env_values_provider,
                config_provider=config_provider,
                status_provider=status_provider,
            )
        )
        self._snapshot = self._snapshot_provider()
        self.selected_handoff_index = 0
        self.last_handoff: AccessHandoff | None = None

    @property
    def snapshot(self) -> AccessSnapshot:
        return self._snapshot

    def refresh(self) -> str:
        self._snapshot = self._snapshot_provider()
        self.selected_handoff_index = min(self.selected_handoff_index, max(len(self._snapshot.handoffs) - 1, 0))
        self.last_handoff = None
        return self.render()

    def render(self) -> str:
        lines = [self.title, self.summary]
        if self._snapshot.notices:
            lines.append("")
            lines.append("Notices:")
            lines.extend(f"- {redact_diagnostic_text(notice)}" for notice in self._snapshot.notices)
        lines.extend(("", "URLs:"))
        lines.extend(_render_url(entry) for entry in self._snapshot.urls)
        lines.extend(("", "Credentials:"))
        lines.extend(_render_credential(entry) for entry in self._snapshot.credentials)
        lines.extend(("", "Recommended actions:"))
        for index, handoff in enumerate(self._snapshot.handoffs):
            marker = ">" if index == self.selected_handoff_index else " "
            lines.append(f"{marker} {handoff.key}  {handoff.label} -> {handoff.workflow_target}: {handoff.summary}")
        lines.extend(("", "Actions:", "up/down  Select handoff", "1-5  Jump to handoff", "enter/o  Handoff to selected workflow", "r  Refresh", "b  Back to menu", "q  Quit"))
        if self.last_handoff is not None:
            lines.extend(("", f"Selected handoff: {self.last_handoff.workflow_target}"))
        return "\n".join(lines)

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"r", "refresh"}:
            self.refresh()
            return WorkflowKeyResult(f"Refreshed {self.id.replace('_', ' ')}.")
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        if key in {"up", "k"}:
            self._move(-1)
            return WorkflowKeyResult("Selected action: previous access handoff.")
        if key in {"down", "j"}:
            self._move(1)
            return WorkflowKeyResult("Selected action: next access handoff.")
        if key.isdigit():
            return self._select_number(key)
        if key in {"enter", "o"}:
            return self._handoff_selected()
        return WorkflowKeyResult(f"No access workflow action is bound to {key!r}.")

    on_key = handle_key

    def _move(self, offset: int) -> None:
        if not self._snapshot.handoffs:
            self.selected_handoff_index = 0
            return
        self.selected_handoff_index = (self.selected_handoff_index + offset) % len(self._snapshot.handoffs)

    def _select_number(self, key: str) -> WorkflowKeyResult:
        for index, handoff in enumerate(self._snapshot.handoffs):
            if handoff.key == key:
                self.selected_handoff_index = index
                return WorkflowKeyResult(f"Selected action {key}: {handoff.label}.")
        return WorkflowKeyResult(f"No access handoff is bound to {key!r}.")

    def _handoff_selected(self) -> WorkflowKeyResult:
        if not self._snapshot.handoffs:
            return WorkflowKeyResult("No access handoff is available.")
        handoff = self._snapshot.handoffs[self.selected_handoff_index]
        self.last_handoff = handoff
        return WorkflowKeyResult(f"Open workflow target: {handoff.workflow_target}.", open_target=handoff.workflow_target)


def build_dashboard_access_workflow(**kwargs) -> AccessWorkflowScreen:
    return AccessWorkflowScreen(
        screen_id="dashboard_access",
        title="Dashboard access",
        summary="Read-only dashboard URL and token-access overview. Secrets are masked and token generation is not executed.",
        **kwargs,
    )


def build_urls_credentials_workflow(**kwargs) -> AccessWorkflowScreen:
    return AccessWorkflowScreen(
        screen_id="urls_credentials",
        title="URLs and credentials",
        summary="Read-only URLs and credential presence overview. Secret values are masked by default.",
        **kwargs,
    )


def _load_values(
    *,
    env_file: Path | str | None,
    env_values_provider: EnvValuesProvider | None,
) -> tuple[Mapping[str, str], list[str]]:
    if env_values_provider is not None:
        return dict(env_values_provider()), []
    env_path = Path(env_file) if env_file is not None else repo_root() / ".env"
    if not env_path.is_file():
        return {}, [".env is unavailable; URL and credential values are shown as missing."]
    try:
        return EnvDocument.read(env_path).values(), []
    except OSError as exc:
        return {}, [f".env could not be read: {exc}"]


def _load_status(status_provider: StatusProvider | None) -> tuple[Mapping[str, str], list[str]]:
    if status_provider is None:
        return {}, []
    status = status_provider()
    component_states = {_component_entry_id(component.name): component.status for component in status.components}
    return component_states, list(status.warnings)


def _component_entry_id(component_name: str) -> str:
    return component_name.replace("-", "_").lower()


def _url_entry(key: str, label: str, values: Mapping[str, str], status_by_id: Mapping[str, str]) -> AccessUrlEntry:
    if key == "dashboard":
        domain = _expand_value(values.get("DOMAIN", ""), values)
        if not domain:
            return AccessUrlEntry(key, label, "<unset>", AccessEntryState.MISSING, ValueVisibility.UNSET, detail="DOMAIN is required")
        return AccessUrlEntry(key, label, f"https://dashboard.{domain}", AccessEntryState.PRESENT, detail="derived from DOMAIN")

    raw_value = values.get(key, "")
    if not raw_value:
        return AccessUrlEntry(key, label, "<unset>", AccessEntryState.MISSING, ValueVisibility.UNSET)
    expanded = _expand_value(raw_value, values)
    state = AccessEntryState.WARN if "$" in expanded else AccessEntryState.PRESENT
    detail = "contains unresolved expression" if state == AccessEntryState.WARN else ""
    return AccessUrlEntry(key, label, expanded, state, detail=detail)


def _credential_entry(key: str, values: Mapping[str, str]) -> CredentialEntry:
    field = field_by_key(key)
    label = field.note or key.replace("_", " ").title()
    raw_value = values.get(key, "")
    if not raw_value:
        required = bool(field and field.required)
        state = AccessEntryState.MISSING if required else AccessEntryState.SKIP
        return CredentialEntry(key, label, "<unset>", state, ValueVisibility.UNSET, detail="required" if required else "optional")
    rendered = redacted_value(key, raw_value)
    visibility = ValueVisibility.MASKED if rendered == "<redacted>" else ValueVisibility.VISIBLE
    return CredentialEntry(key, label, rendered, AccessEntryState.PRESENT, visibility, reveal_supported=False)


def _expand_value(value: str, values: Mapping[str, str]) -> str:
    expanded = value
    for _ in range(4):
        next_value = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", lambda match: values.get(match.group(1), match.group(0)), expanded)
        if next_value == expanded:
            return next_value
        expanded = next_value
    return expanded


def _render_url(entry: AccessUrlEntry) -> str:
    detail = f" - {entry.detail}" if entry.detail else ""
    return redact_diagnostic_text(f"{entry.state.value:<7} {entry.label}: {entry.value}{detail}")


def _render_credential(entry: CredentialEntry) -> str:
    detail = f" - {entry.detail}" if entry.detail else ""
    reveal = " reveal-disabled" if not entry.reveal_supported else ""
    return redact_diagnostic_text(f"{entry.state.value:<7} {entry.label}: {entry.value} [{entry.visibility.value}{reveal}]{detail}")
