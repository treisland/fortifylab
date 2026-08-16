"""Read-only kubectl-backed collectors for dashboard snapshots."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fortifylab.core.command import CommandResult, run_command

from .model import ApplicationHealth, DashboardSnapshot, ResourceSummary, demo_snapshot

Runner = Callable[[tuple[str, ...]], CommandResult]

APP_SELECTORS: tuple[tuple[str, str], ...] = (
    ("Software Security Center", "ssc-webapp"),
    ("License and Infrastructure Manager", "lim"),
    ("ScanCentral SAST Controller", "scancentral-sast-controller"),
    ("ScanCentral SAST Sensor", "scancentral-sast-sensor"),
    ("ScanCentral DAST Core", "scancentral-dast-core"),
    ("ScanCentral DAST Scanner", "scancentral-dast-scanner"),
    ("MySQL", "mysql"),
    ("PostgreSQL", "postgresql"),
)


class DashboardCollector:
    """Build a safe read-only dashboard snapshot from Kubernetes JSON."""

    def __init__(self, *, namespace: str = "fortify", kubectl: str = "microk8s kubectl", runner: Runner | None = None, profile: str = "unknown") -> None:
        self.namespace = namespace
        self.kubectl = tuple(kubectl.split())
        self.runner = runner or self._default_runner
        self.profile = profile

    def collect(self) -> DashboardSnapshot:
        nodes_result = self._get_json("nodes")
        pods_result = self._get_json("pods", namespaced=True)
        pvcs_result = self._get_json("pvc", namespaced=True)
        ingress_result = self._get_json("ingress", namespaced=True)
        events_result = self._get_json("events", namespaced=True)

        first_failure = next((result for result in (nodes_result, pods_result) if result.returncode != 0), None)
        if first_failure is not None:
            message = (first_failure.stderr or first_failure.stdout or "Kubernetes API is unavailable.").strip()
            return DashboardSnapshot(
                overall="unavailable",
                profile=self.profile,
                namespace=self.namespace,
                summary=ResourceSummary(warnings=1),
                applications=(),
                warnings=(message,),
                source="unavailable",
            )

        nodes = _loads(nodes_result.stdout)
        pods = _loads(pods_result.stdout)
        pvcs = _loads(pvcs_result.stdout) if pvcs_result.ok else {}
        ingresses = _loads(ingress_result.stdout) if ingress_result.ok else {}
        events = _loads(events_result.stdout) if events_result.ok else {}

        pod_rows = _pod_rows(pods)
        applications = tuple(_application_health(name, selector, pod_rows) for name, selector in APP_SELECTORS)
        warning_lines = _warning_lines(applications, events)
        ready_pods = sum(1 for pod in pod_rows if pod["ready"] == pod["total"] and pod["total"] > 0 and pod["phase"] == "Running")
        overall = _overall(applications, warning_lines)

        return DashboardSnapshot(
            overall=overall,
            profile=self.profile,
            namespace=self.namespace,
            summary=ResourceSummary(
                pods=len(pod_rows),
                ready_pods=ready_pods,
                pvcs=len(pvcs.get("items", [])),
                ingresses=len(ingresses.get("items", [])),
                nodes_ready=_ready_node_count(nodes),
                warnings=len(warning_lines),
            ),
            applications=applications,
            warnings=tuple(warning_lines),
            source="live",
        )

    def _get_json(self, resource: str, *, namespaced: bool = False) -> CommandResult:
        command = (*self.kubectl, "-n", self.namespace, "get", resource, "-o", "json") if namespaced else (*self.kubectl, "get", resource, "-o", "json")
        return self.runner(command)

    @staticmethod
    def _default_runner(command: tuple[str, ...]) -> CommandResult:
        return run_command(command, timeout=20)


def collect_dashboard(*, demo: bool = False, namespace: str = "fortify", kubectl: str = "microk8s kubectl") -> DashboardSnapshot:
    """Collect a dashboard snapshot, using deterministic demo data when requested."""

    if demo:
        return demo_snapshot()
    return DashboardCollector(namespace=namespace, kubectl=kubectl).collect()


def _loads(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ready_node_count(payload: dict[str, Any]) -> int:
    count = 0
    for item in payload.get("items", []):
        conditions = item.get("status", {}).get("conditions", [])
        if any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in conditions):
            count += 1
    return count


def _pod_rows(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        statuses = item.get("status", {}).get("containerStatuses", [])
        rows.append(
            {
                "name": item.get("metadata", {}).get("name", "unknown"),
                "phase": item.get("status", {}).get("phase", "Unknown"),
                "ready": sum(1 for status in statuses if status.get("ready")),
                "total": len(statuses),
                "restarts": sum(int(status.get("restartCount", 0)) for status in statuses),
            }
        )
    return tuple(rows)


def _application_health(name: str, selector: str, pods: tuple[dict[str, Any], ...]) -> ApplicationHealth:
    matching = tuple(pod for pod in pods if str(pod["name"]).startswith(selector))
    if not matching:
        return ApplicationHealth(name=name, ready="0/0", status="Unknown")
    ready = sum(1 for pod in matching if pod["ready"] == pod["total"] and pod["total"] > 0 and pod["phase"] == "Running")
    restarts = sum(int(pod["restarts"]) for pod in matching)
    phases = {str(pod["phase"]) for pod in matching}
    if ready == len(matching):
        status = "Running"
    elif "Failed" in phases:
        status = "Failed"
    elif "Pending" in phases:
        status = "Pending"
    else:
        status = "NotReady"
    return ApplicationHealth(name=name, ready=f"{ready}/{len(matching)}", status=status, restarts=restarts)


def _warning_lines(applications: tuple[ApplicationHealth, ...], events: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for app in applications:
        if app.status not in {"Running", "Unknown"}:
            warnings.append(f"{app.name} is {app.status} with {app.ready} pods ready.")
    for item in events.get("items", [])[-5:]:
        if item.get("type") == "Warning":
            involved = item.get("involvedObject", {})
            resource = f"{involved.get('kind', 'resource').lower()}/{involved.get('name', 'unknown')}"
            message = item.get("message", "")
            warnings.append(f"{item.get('reason', 'Warning')} {resource}: {message}".strip())
    return warnings


def _overall(applications: tuple[ApplicationHealth, ...], warnings: list[str]) -> str:
    running = [app for app in applications if app.status == "Running"]
    known = [app for app in applications if app.status != "Unknown"]
    if warnings:
        return "warning"
    if known and len(running) == len(known):
        return "healthy"
    return "preview"
