"""Stdlib web console app for local/LAN Fortify Lab previews."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from fortifylab.diagnostics import route_findings
from fortifylab.operations import OperationCatalog
from fortifylab.status import LiveDeploymentSnapshot, LiveStatusPoller, build_service_registry, service_health_payload
from fortifylab.tui.profiles import LOG_SCOPES, build_profile
from fortifylab.web.support import SupportInspector


@dataclass(frozen=True)
class WebConsoleConfig:
    bind_host: str = "127.0.0.1"
    port: int = 8765
    access_token: str | None = None
    allow_lan: bool = False
    env_file: Path | None = None

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        if self.allow_lan and not self.access_token:
            issues.append("LAN access requires an access token.")
        if self.bind_host not in ("127.0.0.1", "localhost") and not self.allow_lan:
            issues.append("Non-local bind requires allow_lan=True.")
        return tuple(issues)


class WebConsoleApp:
    def __init__(
        self,
        config: WebConsoleConfig,
        static_dir: Path | None = None,
        status_poller: Any | None = None,
        url_health_checker: Any | None = None,
        support_inspector: SupportInspector | None = None,
    ) -> None:
        self.config = config
        self.static_dir = static_dir or Path(__file__).with_name("static")
        self.status_poller = status_poller
        self.url_health_checker = url_health_checker
        self.support_inspector = support_inspector

    def is_local_only(self) -> bool:
        return self.config.bind_host in ("127.0.0.1", "localhost")

    def authorize(self, token: str | None) -> bool:
        return self.authorize_request(token)

    def authorize_request(self, token: str | None) -> bool:
        if not self.config.access_token:
            return self.is_local_only()
        return token == self.config.access_token

    def api_response(self, path: str) -> tuple[int, dict[str, Any]]:
        if path == "/api/status":
            operations = OperationCatalog().list()
            return 200, {
                "mode": "lab",
                "operations": [
                    {"id": spec.operation_id, "kind": spec.kind.value, "impact": spec.impact.value}
                    for spec in operations
                ],
            }
        if path == "/api/deployment/status":
            snapshot = self._snapshot()
            payload = snapshot.to_dict()
            payload["event_timeline"] = self.event_timeline_payload(snapshot)
            return 200, payload
        if path == "/api/deployment/guide":
            return 200, self.guided_deployment_payload(self._snapshot())
        if path == "/api/deployment/diagnostics":
            return 200, self.deployment_diagnostics_payload(self._snapshot())
        if path == "/api/deployment/logs":
            return 200, self.deployment_logs_payload(self._snapshot())
        if path == "/api/services":
            return 200, self.service_registry_payload()
        if path == "/api/services/health":
            return 200, self.service_health_payload()
        if path == "/api/routes":
            snapshot = self._snapshot()
            payload = self._support_inspector(snapshot).routes_payload(snapshot)
            payload["findings"] = list(route_findings(()))
            return 200, payload
        if path == "/api/config":
            return 200, {"sections": ["identity", "urls", "versions", "credentials"], "secrets_redacted": True}
        if path == "/api/certificates":
            snapshot = self._snapshot()
            return 200, self._support_inspector(snapshot).certificate_payload(snapshot)
        return 404, {"error": "not found"}

    def _snapshot(self) -> LiveDeploymentSnapshot:
        poller = self.status_poller or LiveStatusPoller()
        return poller.snapshot()

    def _support_inspector(self, snapshot: LiveDeploymentSnapshot) -> SupportInspector:
        if self.support_inspector:
            return self.support_inspector
        return SupportInspector(namespace=snapshot.namespace)

    def _service_registry(self) -> Any:
        return build_service_registry(self.config.env_file)

    def service_registry_payload(self) -> dict[str, Any]:
        return self._service_registry().to_dict()

    def service_health_payload(self) -> dict[str, Any]:
        snapshot = self._snapshot()
        return service_health_payload(self._service_registry(), checker=self.url_health_checker, snapshot=snapshot)

    def guided_deployment_payload(self, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        profile = build_profile(snapshot.profile)
        by_id = {step.step_id: step for step in snapshot.steps}
        steps = []
        for index, profile_step in enumerate(profile.steps, start=1):
            live_step = by_id.get(profile_step.step_id)
            steps.append({
                "index": index,
                "total": len(profile.steps),
                "step_id": profile_step.step_id,
                "label": profile_step.label,
                "state": live_step.state.value if live_step else "pending",
                "detail": live_step.detail if live_step else "Waiting for this step to start.",
                "pods": [pod.name for pod in live_step.pods] if live_step else [],
                "hint_count": len(live_step.hints) if live_step else 0,
            })
        return {"profile": snapshot.profile, "overall_state": snapshot.overall_state.value, "steps": steps}

    def deployment_diagnostics_payload(self, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        findings = []
        for step in snapshot.steps:
            for hint in step.hints:
                findings.append({
                    "step_id": step.step_id,
                    "step_label": step.label,
                    "severity": hint.severity.value,
                    "reason": hint.reason,
                    "message": hint.message,
                    "next_inspection": hint.next_inspection,
                })
        return {"findings": findings, "tool_warnings": list(snapshot.tool_warnings)}

    def event_timeline_payload(self, snapshot: LiveDeploymentSnapshot) -> list[dict[str, Any]]:
        timeline = []
        seen: set[tuple[str, str, str, str | None]] = set()
        for step in snapshot.steps:
            for event in step.events:
                key = (step.step_id, event.reason, event.message, event.age)
                if key in seen:
                    continue
                seen.add(key)
                timeline.append({
                    "step_id": step.step_id,
                    "step_label": step.label,
                    "type": event.type,
                    "reason": event.reason,
                    "object": event.object,
                    "message": event.message,
                    "age": event.age,
                })
        return timeline[-25:]

    def deployment_logs_payload(self, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        resources = []
        for step in snapshot.steps:
            pods = list(step.pods)
            if not pods:
                continue
            scope = LOG_SCOPES.get(step.step_id)
            resources.append({
                "step_id": step.step_id,
                "step_label": step.label,
                "state": step.state.value,
                "scope": scope,
                "selection_required": len(pods) > 1,
                "context": {
                    "detail": step.detail,
                    "hints": [
                        {
                            "severity": hint.severity.value,
                            "reason": hint.reason,
                            "message": hint.message,
                            "next_inspection": hint.next_inspection,
                        }
                        for hint in step.hints
                    ],
                    "events": [
                        {"type": event.type, "reason": event.reason, "object": event.object, "message": event.message, "age": event.age}
                        for event in step.events[-5:]
                    ],
                },
                "pods": [
                    {
                        "number": index,
                        "name": pod.name,
                        "phase": pod.phase,
                        "ready": f"{pod.ready}/{pod.total}",
                        "reason": pod.reason,
                        "restarts": pod.restarts,
                        "recent_command": ["microk8s", "kubectl", "-n", snapshot.namespace, "logs", pod.name, "--tail", "120"],
                        "previous_command": ["microk8s", "kubectl", "-n", snapshot.namespace, "logs", pod.name, "--previous", "--tail", "120"],
                        "follow_command": ["microk8s", "kubectl", "-n", snapshot.namespace, "logs", pod.name, "-f"],
                        "describe_command": ["microk8s", "kubectl", "-n", snapshot.namespace, "describe", "pod", pod.name],
                    }
                    for index, pod in enumerate(pods, start=1)
                ],
            })
        return {"resources": resources}

    def api_envelope(self, path: str) -> tuple[int, dict[str, Any]]:
        status, body = self.api_response(path)
        if status >= 400:
            code = str(body.get("error", "not_found"))
            return status, self.error_envelope(code, "API endpoint not found.")
        return status, {"ok": True, "data": body, "error": None}

    def error_envelope(self, code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "data": None, "error": {"code": code, "message": message}}

    def static_asset(self, relative: str) -> tuple[str, str]:
        safe = relative.lstrip("/") or "index.html"
        if ".." in safe:
            raise FileNotFoundError(safe)
        path = self.static_dir / safe
        if not path.is_file():
            raise FileNotFoundError(safe)
        content_type = "text/html" if path.suffix == ".html" else "text/css" if path.suffix == ".css" else "application/javascript"
        return content_type, path.read_text(encoding="utf-8")

    def json_response(self, path: str) -> str:
        status, body = self.api_response(path)
        return json.dumps({"status": status, "body": body}, indent=2)
