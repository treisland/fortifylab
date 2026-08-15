"""Stdlib web console app for local/LAN Fortify Lab previews."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from fortifylab.diagnostics import route_findings
from fortifylab.operations import ActionPreview, OperationJobManager, OperationJobRequest, OperationSpec
from fortifylab.operations.previews import ActionPreviewCatalog
from fortifylab.status import LiveDeploymentSnapshot, LiveState, LiveStatusPoller, LiveStepStatus, build_service_registry, service_health_payload
from fortifylab.tui.profiles import LOG_SCOPES, build_profile
from fortifylab.web.security import ActionSecurityMode
from fortifylab.web.support import SupportInspector


@dataclass(frozen=True)
class WebConsoleConfig:
    bind_host: str = "127.0.0.1"
    port: int = 8765
    access_token: str | None = None
    allow_lan: bool = False
    env_file: Path | None = None
    enable_actions: bool = False

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
        operation_jobs: OperationJobManager | None = None,
    ) -> None:
        self.config = config
        self.static_dir = static_dir or Path(__file__).with_name("static")
        self.status_poller = status_poller
        self.url_health_checker = url_health_checker
        self.support_inspector = support_inspector
        self.operation_jobs = operation_jobs or OperationJobManager()

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
            return 200, {
                "mode": "lab",
                "security": self.action_security_payload(),
                "operations": [
                    {"id": item["id"], "kind": item["kind"], "impact": item["impact"]}
                    for item in self.operation_jobs.operation_payloads()
                ],
            }
        if path == "/api/security/posture":
            return 200, self.security_posture_payload()
        if path == "/api/lifecycle/actions":
            return 200, self.lifecycle_actions_payload()
        if path == "/api/lifecycle/audit":
            return 200, self.lifecycle_audit_payload()
        if path == "/api/actions":
            return 200, self.action_catalog_payload()
        if path.startswith("/api/actions/"):
            operation_id = path.removeprefix("/api/actions/")
            preview = self._action_preview_catalog().get(operation_id)
            if preview is None:
                return 404, {"error": "action not found"}
            return 200, {"security": self.action_security_payload(), "action": preview.to_dict()}
        if path == "/api/operations":
            return 200, {"operations": self.operation_jobs.operation_payloads()}
        if path == "/api/operations/jobs":
            return 200, {"jobs": [job.to_api_dict() for job in self.operation_jobs.list_jobs()]}
        if path.startswith("/api/operations/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            job = self.operation_jobs.get_job(job_id)
            if job is None:
                return 404, {"error": "not found"}
            return 200, {"job": job.to_api_dict()}
        if path == "/api/operations/audit":
            return 200, {"entries": [entry.to_api_dict() for entry in self.operation_jobs.audit_entries()]}
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

    def api_mutation_response(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/api/operations/jobs":
            try:
                request = OperationJobRequest.from_payload(payload)
                spec = self.operation_jobs.catalog.get(request.operation_id)
                if request.execute and spec.mutates and not self.config.enable_actions:
                    return 403, {"error": "Action execution is disabled; restart the web console with --enable-actions."}
                job, created = self.operation_jobs.submit(request)
            except ValueError as exc:
                return 400, {"error": str(exc)}
            return (202 if created else 200), {"job": job.to_api_dict(), "created": created}
        return 404, {"error": "not found"}

    def action_security_payload(self) -> dict[str, Any]:
        return ActionSecurityMode(enable_actions=self.config.enable_actions).to_dict()

    def action_catalog_payload(self) -> dict[str, Any]:
        previews = self._action_preview_catalog().list()
        return {
            "security": self.action_security_payload(),
            "confirmation_contract": {
                "comparison": "exact",
                "case_sensitive": True,
                "field": "confirmation_phrase",
            },
            "actions": [preview.to_dict() for preview in previews],
        }

    def _action_preview_catalog(self) -> ActionPreviewCatalog:
        return ActionPreviewCatalog(enable_actions=self.config.enable_actions)

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

    def security_posture_payload(self) -> dict[str, Any]:
        return {
            "console": {
                "bind_host": self.config.bind_host,
                "local_only": self.is_local_only(),
                "lan_access": self.config.allow_lan,
                "token_required": bool(self.config.access_token),
            },
            "actions": self.action_security_payload(),
            "boundaries": [
                "Lifecycle execution is disabled unless the console is started with action execution enabled.",
                "Mutating operations require an explicit backend action endpoint before they can run.",
                "Destructive operations require exact typed confirmation and recovery review.",
                "Secrets, private keys, licenses, and token values are never returned by the console APIs.",
            ],
        }

    def lifecycle_actions_payload(self) -> dict[str, Any]:
        action_payload = self.action_catalog_payload()
        execute_enabled = bool(action_payload["security"].get("enable_actions"))
        snapshot = self._snapshot()
        specs = self._dynamic_lifecycle_specs(snapshot)
        actions = [self._lifecycle_action_payload(spec, snapshot) for spec in specs]
        return {
            "mode": "actions_enabled" if execute_enabled else "preview_only",
            "execute_endpoint": "/api/operations/jobs",
            "security": action_payload["security"],
            "confirmation_contract": action_payload["confirmation_contract"],
            "actions": actions,
        }

    def _dynamic_lifecycle_specs(self, snapshot: LiveDeploymentSnapshot) -> list[OperationSpec]:
        catalog = self.operation_jobs.catalog
        specs: list[OperationSpec] = [catalog.certs(), catalog.secrets(), catalog.cluster("start"), catalog.cluster("stop")]
        seen = {spec.operation_id for spec in specs}
        for step in snapshot.steps:
            app_id = _app_id_for_step(step.step_id)
            if app_id:
                action = "stop" if _step_has_running_workload(step) else "start"
                for spec in (catalog.app(app_id, action), catalog.app(app_id, "destroy")):
                    if spec.operation_id not in seen:
                        specs.append(spec)
                        seen.add(spec.operation_id)
            for pod in step.pods:
                spec = catalog.logs(pod.name, follow=False)
                if spec.operation_id not in seen:
                    specs.append(spec)
                    seen.add(spec.operation_id)
        return specs

    def _lifecycle_action_payload(self, spec: OperationSpec, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        preview = ActionPreview(spec, self.config.enable_actions and spec.mutates).to_dict()
        resource = _resource_for_operation(spec.operation_id, snapshot)
        for sensitive_key in ("command", "command_display", "command_preview"):
            preview.pop(sensitive_key, None)
        preview.update({
            "resource": resource,
            "job": {
                "state": "not_started",
                "message": "No lifecycle job has been submitted from the web console.",
            },
        })
        return preview

    def lifecycle_audit_payload(self) -> dict[str, Any]:
        entries = [entry.to_api_dict() for entry in self.operation_jobs.audit_entries()]
        return {
            "entries": entries,
            "placeholder": "Lifecycle audit entries will appear here after backend execution wiring records action requests.",
            "redaction": "Commands and output are redacted before display.",
        }

    def guided_deployment_payload(self, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        profile = build_profile(snapshot.profile)
        by_id = {step.step_id: step for step in snapshot.steps}
        steps = []
        for index, profile_step in enumerate(profile.steps, start=1):
            live_step = by_id.get(profile_step.step_id)
            state = live_step.state.value if live_step else "pending"
            detail = live_step.detail if live_step else "Waiting for this step to start."
            steps.append({
                "index": index,
                "total": len(profile.steps),
                "step_id": profile_step.step_id,
                "label": profile_step.label,
                "state": state,
                "detail": detail,
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
        return self._envelope(status, body)

    def api_mutation_envelope(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        status, body = self.api_mutation_response(path, payload)
        return self._envelope(status, body)

    def _envelope(self, status: int, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if status >= 400:
            code = str(body.get("error", "not_found"))
            message = code if code != "not found" else "API endpoint not found."
            return status, self.error_envelope(code, message)
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


def _step_has_live_evidence(step: LiveStepStatus | None) -> bool:
    if step is None:
        return False
    if step.state is not LiveState.PENDING:
        return True
    return bool(step.pods or step.events or step.routes or step.hints)


APP_STEP_IDS = {
    "mysql": "mysql",
    "postgresql": "postgresql",
    "ssc": "ssc",
    "lim": "lim",
    "scsast": "scsast",
    "scsast_ctrl": "scsast",
    "scdast_core": "scdast-core",
    "scdast": "scdast-core",
    "scdast_scanner": "scdast-scanner",
}


def _app_id_for_step(step_id: str) -> str | None:
    return APP_STEP_IDS.get(step_id)


def _step_has_running_workload(step: LiveStepStatus) -> bool:
    return bool(step.pods)


def _resource_for_operation(operation_id: str, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
    if operation_id.startswith("cluster."):
        return {"id": "cluster", "label": "MicroK8s cluster", "state": snapshot.overall_state.value, "scope": "cluster"}
    if operation_id.startswith("logs."):
        pod_name = operation_id.removeprefix("logs.")
        for step in snapshot.steps:
            if any(pod.name == pod_name for pod in step.pods):
                return {"id": pod_name, "label": pod_name, "state": step.state.value, "scope": "pod", "step_id": step.step_id, "step_label": step.label}
        return {"id": pod_name, "label": pod_name, "state": "unknown", "scope": "pod"}
    if operation_id.startswith("app."):
        app_id = operation_id.split(".")[1]
        for step in snapshot.steps:
            if _app_id_for_step(step.step_id) == app_id:
                return {"id": app_id, "label": step.label, "state": step.state.value, "scope": "application", "step_id": step.step_id}
        return {"id": app_id, "label": app_id, "state": "not_deployed", "scope": "application"}
    return {"id": "maintenance", "label": "Maintenance", "state": "available", "scope": "maintenance"}
