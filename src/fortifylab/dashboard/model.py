"""Read-only dashboard snapshot models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationHealth:
    name: str
    ready: str
    status: str
    restarts: int = 0


@dataclass(frozen=True)
class ResourceSummary:
    pods: int = 0
    ready_pods: int = 0
    pvcs: int = 0
    ingresses: int = 0
    nodes_ready: int = 0
    warnings: int = 0


@dataclass(frozen=True)
class DashboardSnapshot:
    overall: str
    profile: str
    namespace: str
    summary: ResourceSummary
    applications: tuple[ApplicationHealth, ...]
    warnings: tuple[str, ...] = ()
    source: str = "demo"


def demo_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        overall="preview",
        profile="full_lab",
        namespace="fortify",
        summary=ResourceSummary(pods=3, ready_pods=2, pvcs=2, ingresses=2, nodes_ready=1, warnings=1),
        applications=(
            ApplicationHealth("Software Security Center", "1/1", "Running"),
            ApplicationHealth("MySQL", "1/1", "Running"),
            ApplicationHealth("ScanCentral SAST", "0/1", "Pending"),
        ),
        warnings=("ScanCentral SAST is waiting for matching pods or endpoints.",),
        source="demo",
    )
