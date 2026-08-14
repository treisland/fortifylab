"""Contracts for the companion web console."""

from __future__ import annotations

import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fortifylab.core.command import CommandResult
from fortifylab.operations import OperationJobManager, OperationJobRequest, OperationRunner
from fortifylab.status import EventSummary, HintSeverity, LiveDeploymentSnapshot, LiveState, LiveStepStatus, PodSummary, ProgressHint, RouteSummary
from fortifylab.web import WebConsoleApp, WebConsoleConfig, build_http_server
from fortifylab.web.support import SupportInspector


class PythonWebConsoleTests(unittest.TestCase):
    def request_once(self, config: WebConsoleConfig, path: str, *, headers: dict[str, str] | None = None, data: dict[str, object] | None = None):
        server = build_http_server(config)
        host, port = server.server_address[:2]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
            request_headers = dict(headers or {})
            if body_bytes is not None:
                request_headers.setdefault("Content-Type", "application/json")
            request = Request(f"http://{host}:{port}{path}", headers=request_headers, data=body_bytes)
            response = urlopen(request, timeout=5)
            body = response.read().decode("utf-8")
            return response.status, dict(response.headers), body
        finally:
            thread.join(timeout=5)
            server.server_close()

    def test_lan_access_requires_token(self) -> None:
        config = WebConsoleConfig(bind_host="0.0.0.0", allow_lan=True)

        self.assertIn("LAN access requires an access token.", config.validate())

    def test_non_local_bind_requires_explicit_lan_mode(self) -> None:
        config = WebConsoleConfig(bind_host="0.0.0.0", access_token="token")

        self.assertIn("Non-local bind requires allow_lan=True.", config.validate())

    def test_authorization_accepts_matching_token(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(bind_host="0.0.0.0", allow_lan=True, access_token="token"))

        self.assertFalse(app.authorize(None))
        self.assertTrue(app.authorize("token"))

    def test_status_api_exposes_operation_summaries_without_secrets(self) -> None:
        status, body = WebConsoleApp(WebConsoleConfig()).api_response("/api/status")

        self.assertEqual(status, 200)
        self.assertIn("operations", body)
        self.assertNotIn("password", str(body).lower())
        self.assertNotIn("token", str(body).lower())

    def test_static_console_loads_operator_panels(self) -> None:
        content_type, html = WebConsoleApp(WebConsoleConfig()).static_asset("index.html")

        self.assertEqual(content_type, "text/html")
        for expected in ('data-panel="deployment"', 'data-panel="configuration"', 'data-panel="routes"', 'data-panel="certificates"', 'data-panel="lifecycle"', 'data-panel="security"', 'data-panel="audit"'):
            self.assertIn(expected, html)
        for expected in ('data-theme-choice="system"', 'data-theme-choice="light"', 'data-theme-choice="dark"'):
            self.assertIn(expected, html)

        _, script = WebConsoleApp(WebConsoleConfig()).static_asset("main.js")
        _, styles = WebConsoleApp(WebConsoleConfig()).static_asset("styles.css")
        self.assertIn("/api/services/health", script)
        self.assertIn("/api/security/posture", script)
        self.assertIn("/api/lifecycle/actions", script)
        self.assertIn("/api/lifecycle/audit", script)
        self.assertIn("fallbackLifecycleActions", script)
        self.assertIn("Execution disabled", script)
        self.assertIn("refreshIntervalMs = 5000", script)
        self.assertIn("window.setInterval(refreshConsole, refreshIntervalMs)", script)
        self.assertIn("fortifylab.theme", script)
        self.assertIn(":root[data-theme=\"dark\"]", styles)
        self.assertIn("prefers-color-scheme: dark", styles)
        self.assertIn("uptime-strip", styles)
        self.assertIn("lifecycle-layout", styles)
        self.assertIn("confirmation-box", styles)

    def test_serve_once_returns_static_index(self) -> None:
        status, headers, body = self.request_once(WebConsoleConfig(port=0), "/")

        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("Fortify Lab Console", body)

    def test_serve_once_status_api_returns_json_envelope(self) -> None:
        status, headers, body = self.request_once(WebConsoleConfig(port=0), "/api/status")
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertTrue(payload["ok"])
        self.assertIn("operations", payload["data"])

    def test_unknown_api_path_returns_json_404(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request_once(WebConsoleConfig(port=0), "/api/unknown")

        self.assertEqual(raised.exception.code, 404)
        payload = json.loads(raised.exception.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "not found")

    def test_lan_api_without_token_returns_401(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request_once(WebConsoleConfig(port=0, access_token="token"), "/api/status")

        self.assertEqual(raised.exception.code, 401)
        payload = json.loads(raised.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_lan_api_accepts_bearer_token(self) -> None:
        status, _, body = self.request_once(
            WebConsoleConfig(port=0, access_token="token"),
            "/api/status",
            headers={"Authorization": "Bearer token"},
        )
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_lan_static_accepts_token_query_and_sets_cookie(self) -> None:
        status, headers, body = self.request_once(WebConsoleConfig(port=0, access_token="token"), "/?token=token")

        self.assertEqual(status, 200)
        self.assertIn("Fortify Lab Console", body)
        self.assertIn("fortifylab_token=token", headers.get("Set-Cookie", ""))

    def test_static_path_traversal_is_blocked(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request_once(WebConsoleConfig(port=0), "/%2e%2e/secrets")

        self.assertEqual(raised.exception.code, 404)


    def test_operations_api_exposes_job_payload_helpers(self) -> None:
        manager = OperationJobManager(runner=OperationRunner(lambda command: CommandResult(command, 0, "logs", "", 0.01)))
        app = WebConsoleApp(WebConsoleConfig(), operation_jobs=manager)

        status, create_payload = app.api_mutation_envelope("/api/operations/jobs", {"operation_id": "logs.ssc-webapp-0"})
        job = wait_for_web_job(manager, create_payload["data"]["job"]["job_id"])
        list_status, list_payload = app.api_envelope("/api/operations/jobs")
        audit_status, audit_payload = app.api_envelope("/api/operations/audit")

        self.assertEqual(status, 202)
        self.assertTrue(create_payload["ok"])
        self.assertEqual(job.status.value, "complete")
        self.assertEqual(list_status, 200)
        self.assertEqual(list_payload["data"]["jobs"][0]["operation_id"], "logs.ssc-webapp-0")
        self.assertEqual(audit_status, 200)
        self.assertGreaterEqual(len(audit_payload["data"]["entries"]), 3)

    def test_operations_post_endpoint_creates_dry_run_job(self) -> None:
        status, headers, body = self.request_once(
            WebConsoleConfig(port=0),
            "/api/operations/jobs",
            data={"operation_id": "app.ssc.stop"},
        )
        payload = json.loads(body)

        self.assertEqual(status, 202)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["job"]["execute"])

    def test_api_endpoints_cover_status_config_routes_certificates(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(), status_poller=FakeStatusPoller(), url_health_checker=FakeURLHealthChecker())

        for path in ("/api/status", "/api/config", "/api/routes", "/api/certificates", "/api/services", "/api/services/health", "/api/security/posture", "/api/lifecycle/actions", "/api/lifecycle/audit", "/api/deployment/status", "/api/deployment/guide", "/api/deployment/diagnostics", "/api/deployment/logs"):
            with self.subTest(path=path):
                status, payload = app.api_envelope(path)
                self.assertEqual(status, 200)
                self.assertTrue(payload["ok"])
                self.assertIsNone(payload["error"])

    def test_lifecycle_action_preview_is_read_only_and_redacted(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(bind_host="0.0.0.0", allow_lan=True, access_token="token"))

        _, posture = app.api_envelope("/api/security/posture")
        _, actions = app.api_envelope("/api/lifecycle/actions")
        _, audit = app.api_envelope("/api/lifecycle/audit")

        self.assertTrue(posture["data"]["actions"]["read_only"])
        self.assertTrue(posture["data"]["console"]["token_required"])
        self.assertEqual(actions["data"]["mode"], "preview_only")
        self.assertIsNone(actions["data"]["execute_endpoint"])
        destroy = next(action for action in actions["data"]["actions"] if action["id"] == "app.ssc.destroy")
        self.assertEqual(destroy["confirmation"]["phrase"], "DESTROY ssc")
        self.assertIn("./apps/ssc/destroy.sh", destroy["command_preview"])
        self.assertNotIn("password", str(actions).lower())
        self.assertEqual(audit["data"]["entries"], [])

    def test_deployment_status_api_returns_steps_and_event_timeline(self) -> None:
        status, payload = WebConsoleApp(WebConsoleConfig(), status_poller=FakeStatusPoller()).api_envelope("/api/deployment/status")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("steps", payload["data"])
        self.assertEqual(payload["data"]["event_timeline"][0]["step_id"], "ssc")
        self.assertEqual(payload["data"]["event_timeline"][0]["reason"], "ImagePullBackOff")

    def test_guided_deployment_api_returns_ordered_steps(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(), status_poller=FakeStatusPoller())
        status, payload = app.api_envelope("/api/deployment/guide")

        self.assertEqual(status, 200)
        steps = payload["data"]["steps"]
        self.assertEqual(steps[0]["index"], 1)
        self.assertEqual(steps[0]["total"], len(steps))
        self.assertTrue(any(step["step_id"] == "ssc" and step["state"] == "blocked" for step in steps))

    def test_guided_deployment_marks_prior_no_pod_steps_complete_when_later_step_is_active(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(), status_poller=FakeMysqlDeployingPoller())
        _, payload = app.api_envelope("/api/deployment/guide")

        steps = payload["data"]["steps"]
        by_id = {step["step_id"]: step for step in steps}
        self.assertEqual(by_id["prereqs"]["state"], "complete")
        self.assertEqual(by_id["inputs"]["state"], "complete")
        self.assertEqual(by_id["secrets"]["state"], "complete")
        self.assertEqual(by_id["mysql"]["state"], "in_progress")

    def test_deployment_diagnostics_are_contextual_and_redacted(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(), status_poller=FakeStatusPoller())
        _, payload = app.api_envelope("/api/deployment/diagnostics")

        findings = payload["data"]["findings"]
        self.assertEqual(findings[0]["step_id"], "ssc")
        self.assertIn("registry", findings[0]["next_inspection"].lower())
        self.assertNotIn("password", str(payload).lower())

    def test_deployment_logs_api_numbers_resources_and_skips_selection_for_single_match(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(), status_poller=FakeStatusPoller())
        _, payload = app.api_envelope("/api/deployment/logs")

        resources = payload["data"]["resources"]
        ssc = next(resource for resource in resources if resource["step_id"] == "ssc")
        self.assertFalse(ssc["selection_required"])
        self.assertEqual(ssc["pods"][0]["number"], 1)
        self.assertIn("logs", ssc["pods"][0]["recent_command"])
        self.assertIn("describe", ssc["pods"][0]["describe_command"])
        self.assertIn("previous_command", ssc["pods"][0])
        self.assertEqual(ssc["context"]["events"][0]["reason"], "ImagePullBackOff")

    def test_routes_api_returns_hosts_entry_hints_from_ingress_evidence(self) -> None:
        app = WebConsoleApp(
            WebConsoleConfig(),
            status_poller=FakeStatusPoller(),
            support_inspector=SupportInspector(runner=fake_support_runner),
        )
        _, payload = app.api_envelope("/api/routes")

        hints = payload["data"]["hosts_entry_hints"]
        self.assertEqual(hints["target_ip"], "10.0.0.5")
        self.assertEqual(hints["entries"][0]["line"], "10.0.0.5 ssc.fortifydemo.local")
        self.assertFalse(hints["managed_by_console"])

    def test_certificates_api_reports_inventory_and_traefik_default_cert_evidence(self) -> None:
        app = WebConsoleApp(
            WebConsoleConfig(),
            status_poller=FakeStatusPoller(),
            support_inspector=SupportInspector(runner=fake_support_runner),
        )
        _, payload = app.api_envelope("/api/certificates")

        data = payload["data"]
        tls = next(item for item in data["inventory"] if item["name"] == "tls")
        self.assertTrue(tls["present"])
        self.assertTrue(tls["certificate_present"])
        self.assertTrue(tls["private_key_present"])
        self.assertFalse(data["private_key_exported"])
        self.assertEqual(data["traefik_default_certificate"]["status"], "configured")
        self.assertNotIn("PRIVATE KEY", str(data))



class FakeURLHealthChecker:
    def check(self, service):
        return {
            "service_id": service.service_id,
            "label": service.label,
            "url": service.url,
            "host": service.host,
            "checks": {
                "dns": {"state": "ok", "message": "DNS resolves."},
                "tls": {"state": "ok", "message": "TLS ok."},
                "http": {"state": "ok", "message": "HTTP returned 200.", "status_code": 200},
            },
            "hints": [],
        }


def fake_support_runner(command: tuple[str, ...]) -> CommandResult:
    joined = " ".join(command)
    if "get nodes" in joined:
        return CommandResult(command, 0, json.dumps({"items": [{"status": {"addresses": [{"type": "InternalIP", "address": "10.0.0.5"}]}}]}), "", 0)
    if "get secrets" in joined:
        return CommandResult(command, 0, json.dumps({"items": [{"metadata": {"name": "tls"}, "type": "kubernetes.io/tls", "data": {"tls.crt": "Q0VSVA==", "tls.key": "redacted"}}]}), "", 0)
    if "-n ingress get pods" in joined:
        return CommandResult(command, 0, json.dumps({"items": [{"spec": {"containers": [{"args": ["--default-ssl-certificate=fortify/tls"]}]}}]}), "", 0)
    return CommandResult(command, 1, "", "not found", 0)


class FakeStatusPoller:
    def snapshot(self) -> LiveDeploymentSnapshot:
        return LiveDeploymentSnapshot(
            namespace="fortify",
            profile="ssc_only",
            generated_at="2026-08-14T00:00:00+00:00",
            overall_state=LiveState.BLOCKED,
            steps=(
                LiveStepStatus(
                    step_id="mysql",
                    label="MySQL",
                    state=LiveState.COMPLETE,
                    detail="ready",
                    pods=(PodSummary("mysql-0", 1, 1, "Running"),),
                ),
                LiveStepStatus(
                    step_id="ssc",
                    label="Software Security Center",
                    state=LiveState.BLOCKED,
                    detail="image pull blocked",
                    pods=(PodSummary("ssc-webapp-0", 0, 1, "Running", reason="ImagePullBackOff"),),
                    events=(EventSummary("Warning", "ImagePullBackOff", "pod/ssc-webapp-0", "Back-off pulling image"),),
                    routes=(RouteSummary("ssc.fortifydemo.local", True, tls_secret="tls", service_name="ssc-webapp", endpoints_ready=True),),
                    hints=(ProgressHint("ssc", HintSeverity.BLOCKED, "image", "Image pull blocked.", "Check registry credentials."),),
                ),
            ),
        )


class FakeMysqlDeployingPoller:
    def snapshot(self) -> LiveDeploymentSnapshot:
        return LiveDeploymentSnapshot(
            namespace="fortify",
            profile="full_lab",
            generated_at="2026-08-14T00:00:00+00:00",
            overall_state=LiveState.IN_PROGRESS,
            steps=(
                LiveStepStatus(
                    step_id="mysql",
                    label="MySQL",
                    state=LiveState.IN_PROGRESS,
                    detail="Waiting for MySQL readiness.",
                    pods=(PodSummary("mysql-0", 0, 1, "Running"),),
                ),
            ),
        )


def wait_for_web_job(manager: OperationJobManager, job_id: str, *, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get_job(job_id)
        if job and not job.active:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


if __name__ == "__main__":
    unittest.main()
