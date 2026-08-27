"""M9.8 public contract for dashboard access, URLs, and credentials."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from fortifylab.config.schema import fields_for_section, redacted_value
from fortifylab.status import LabStatus, build_check_status
from fortifylab.tui.access import (
    DEFAULT_ACCESS_HANDOFFS,
    URL_FIELDS,
    AccessEntryState,
    AccessHandoff,
    AccessSnapshot,
    AccessUrlEntry,
    AccessWorkflowScreen,
    CredentialEntry,
    ValueVisibility,
    build_access_snapshot,
)


class AccessState(str, Enum):
    """Contract state for dashboard and URL/credential access rendering."""

    PASS = "PASS"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass(frozen=True)
class DashboardAccessEntry:
    """One dashboard-adjacent access URL with clone-safe readiness context."""

    id: str
    label: str
    url: str
    state: AccessState
    detail: str = ""


@dataclass(frozen=True)
class UrlCredentialEntry:
    """One URL or credential value rendered for the URLs/credentials screen."""

    key: str
    label: str
    rendered_value: str
    state: AccessState
    detail: str = ""


@dataclass(frozen=True)
class DashboardAccessSnapshot:
    """Read-only dashboard access snapshot used by the TUI screen."""

    entries: tuple[DashboardAccessEntry, ...]
    recommended_actions: tuple[AccessHandoff, ...]
    notes: tuple[str, ...] = ()

    @property
    def state(self) -> AccessState:
        return _aggregate_state(entry.state for entry in self.entries)


@dataclass(frozen=True)
class UrlsCredentialsSnapshot:
    """Read-only URL and credential snapshot used by the TUI screen."""

    entries: tuple[UrlCredentialEntry, ...]
    recommended_actions: tuple[AccessHandoff, ...]
    notes: tuple[str, ...] = ()

    @property
    def state(self) -> AccessState:
        return _aggregate_state(entry.state for entry in self.entries)


ConfigProvider = Callable[[], Mapping[str, str]]
StatusProvider = Callable[[], LabStatus]
DashboardSnapshotProvider = Callable[[], DashboardAccessSnapshot]
UrlsCredentialsSnapshotProvider = Callable[[], UrlsCredentialsSnapshot]


DASHBOARD_COMPONENTS: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Kubernetes Dashboard", "dashboard"),
    ("ssc", "SSC", "ssc"),
    ("lim", "LIM", "lim"),
    ("scancentral_sast", "ScanCentral SAST", "scancentral-sast"),
    ("scancentral_dast", "ScanCentral DAST", "scancentral-dast"),
)


COMPONENT_URL_KEYS: Mapping[str, str] = {
    "dashboard": "dashboard",
    "ssc": "SSC_URL",
    "lim": "LIM_URL",
    "scancentral_sast": "SCSAST_URL",
    "scancentral_dast": "SCDAST_URL",
}


def mask_secret(key: str, value: str | None) -> str:
    """Render a value without exposing credential-shaped fields."""

    return redacted_value(key, value)


def build_dashboard_access_snapshot(
    *,
    config_provider: ConfigProvider | None = None,
    status_provider: StatusProvider | None = None,
) -> DashboardAccessSnapshot:
    """Build dashboard/access entries from injected config and status providers."""

    values = dict(config_provider() if config_provider is not None else {})
    status = (status_provider or build_check_status)()
    base = build_access_snapshot(env_values_provider=lambda: values)
    urls = {entry.key: entry.value for entry in base.urls}
    component_states = {component.name: component for component in status.components}
    entries: list[DashboardAccessEntry] = []
    for entry_id, label, component_name in DASHBOARD_COMPONENTS:
        url = urls.get(COMPONENT_URL_KEYS[entry_id], "<unset>")
        url_state = AccessState.WARN if url == "<unset>" else AccessState.PASS
        component = component_states.get(component_name)
        component_state = _component_access_state(component) if component is not None else url_state
        detail = component.message if component is not None else "status unavailable in clone-safe mode"
        entries.append(DashboardAccessEntry(entry_id, label, url, _worst_state(url_state, component_state), detail))
    notes = tuple(status.warnings) if status.warnings else ("clone-safe status only; no live cluster queried",)
    return DashboardAccessSnapshot(tuple(entries), DEFAULT_ACCESS_HANDOFFS, notes)


def build_urls_credentials_snapshot(
    *,
    config_provider: ConfigProvider | None = None,
    status_provider: StatusProvider | None = None,
) -> UrlsCredentialsSnapshot:
    """Build URL and credential entries from injected config/status providers."""

    del status_provider
    values = dict(config_provider() if config_provider is not None else {})
    base = build_access_snapshot(env_values_provider=lambda: values)
    entries: list[UrlCredentialEntry] = []
    for key, label in URL_FIELDS:
        if key == "dashboard":
            continue
        access_entry = next(entry for entry in base.urls if entry.key == key)
        state = AccessState.PASS if access_entry.state == AccessEntryState.PRESENT else AccessState.WARN
        entries.append(UrlCredentialEntry(key, label, access_entry.value, state, access_entry.detail))
    for field in fields_for_section("credentials"):
        rendered = mask_secret(field.key, values.get(field.key))
        state = AccessState.PASS if rendered != "<unset>" else AccessState.WARN if field.required else AccessState.SKIP
        entries.append(UrlCredentialEntry(field.key, field.key.replace("_", " ").title(), rendered, state))
    return UrlsCredentialsSnapshot(tuple(entries), DEFAULT_ACCESS_HANDOFFS, tuple(base.notices))


class DashboardAccessScreen(AccessWorkflowScreen):
    """Functional TUI contract screen for the Dashboard access menu path."""

    def __init__(self, *, snapshot_provider: DashboardSnapshotProvider | None = None, **kwargs) -> None:
        provider = (lambda: _dashboard_to_access_snapshot(snapshot_provider())) if snapshot_provider is not None else None
        super().__init__(
            screen_id="dashboard_access",
            title="Dashboard access",
            summary="Read-only Dashboard access overview. URLs are visible; tokens are not generated or revealed.",
            snapshot_provider=provider,
            **kwargs,
        )


class UrlsCredentialsScreen(AccessWorkflowScreen):
    """Functional TUI contract screen for the URLs and credentials menu path."""

    def __init__(self, *, snapshot_provider: UrlsCredentialsSnapshotProvider | None = None, **kwargs) -> None:
        provider = (lambda: _urls_credentials_to_access_snapshot(snapshot_provider())) if snapshot_provider is not None else None
        super().__init__(
            screen_id="urls_credentials",
            title="URLs and credentials",
            summary="Read-only URLs and credential presence overview. Secret values are masked by default.",
            snapshot_provider=provider,
            **kwargs,
        )


def build_dashboard_access_workflow(**kwargs) -> DashboardAccessScreen:
    return DashboardAccessScreen(**kwargs)


def build_urls_credentials_workflow(**kwargs) -> UrlsCredentialsScreen:
    return UrlsCredentialsScreen(**kwargs)


def _component_access_state(component) -> AccessState:
    if component.ok:
        return AccessState.PASS
    return AccessState.WARN


def _dashboard_to_access_snapshot(snapshot: DashboardAccessSnapshot) -> AccessSnapshot:
    urls = tuple(
        AccessUrlEntry(entry.id, entry.label, entry.url, _entry_state(entry.state), detail=entry.detail)
        for entry in snapshot.entries
    )
    credentials = (
        CredentialEntry("dashboard.viewer.token", "Dashboard viewer token", "<unavailable>", AccessEntryState.SKIP, ValueVisibility.UNAVAILABLE, "kubernetes-dashboard", "token generation is not run by this screen"),
    )
    return AccessSnapshot(urls, credentials, snapshot.recommended_actions, snapshot.notes)


def _urls_credentials_to_access_snapshot(snapshot: UrlsCredentialsSnapshot) -> AccessSnapshot:
    urls = tuple(
        AccessUrlEntry(entry.key, entry.label, entry.rendered_value, _entry_state(entry.state), detail=entry.detail)
        for entry in snapshot.entries
        if entry.key.endswith("_URL")
    )
    credentials = tuple(
        CredentialEntry(entry.key, entry.label, entry.rendered_value, _entry_state(entry.state), _visibility_for_rendered(entry.rendered_value), detail=entry.detail)
        for entry in snapshot.entries
        if not entry.key.endswith("_URL")
    )
    return AccessSnapshot(urls, credentials, snapshot.recommended_actions, snapshot.notes)


def _entry_state(state: AccessState) -> AccessEntryState:
    if state == AccessState.PASS:
        return AccessEntryState.PRESENT
    if state == AccessState.SKIP:
        return AccessEntryState.SKIP
    return AccessEntryState.WARN


def _visibility_for_rendered(value: str) -> ValueVisibility:
    if value == "<redacted>":
        return ValueVisibility.MASKED
    if value == "<unset>":
        return ValueVisibility.UNSET
    return ValueVisibility.VISIBLE


def _aggregate_state(states: Iterable[AccessState]) -> AccessState:
    collected = tuple(states)
    if any(state == AccessState.WARN for state in collected):
        return AccessState.WARN
    if collected and all(state == AccessState.SKIP for state in collected):
        return AccessState.SKIP
    return AccessState.PASS


def _worst_state(first: AccessState, second: AccessState) -> AccessState:
    if AccessState.WARN in {first, second}:
        return AccessState.WARN
    if AccessState.SKIP in {first, second}:
        return AccessState.SKIP
    return AccessState.PASS
