"""Shared live deployment status models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class LiveState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class HintSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PodSummary:
    name: str
    ready: int
    total: int
    phase: str
    reason: str | None = None
    restarts: int = 0


@dataclass(frozen=True)
class EventSummary:
    type: str
    reason: str
    object: str
    message: str
    age: str | None = None


@dataclass(frozen=True)
class RouteSummary:
    host: str
    ingress_present: bool
    tls_secret: str | None = None
    service_name: str | None = None
    endpoints_ready: bool = False


@dataclass(frozen=True)
class HelmReleaseSummary:
    name: str
    status: str
    chart: str | None = None
    revision: str | None = None


@dataclass(frozen=True)
class ProgressHint:
    step_id: str
    severity: HintSeverity
    reason: str
    message: str
    next_inspection: str


@dataclass(frozen=True)
class LiveStepStatus:
    step_id: str
    label: str
    state: LiveState
    detail: str
    elapsed_seconds: int = 0
    timeout_seconds: int | None = None
    pods: tuple[PodSummary, ...] = ()
    events: tuple[EventSummary, ...] = ()
    routes: tuple[RouteSummary, ...] = ()
    hints: tuple[ProgressHint, ...] = ()


@dataclass(frozen=True)
class LiveDeploymentSnapshot:
    namespace: str
    profile: str
    generated_at: str
    overall_state: LiveState
    steps: tuple[LiveStepStatus, ...]
    helm_releases: tuple[HelmReleaseSummary, ...] = ()
    tool_warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _plain(asdict(self))


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
