"""Contracts for Phase 5 service registry and URL health APIs."""

from __future__ import annotations

import unittest

from fortifylab.status import LiveDeploymentSnapshot, LiveState, LiveStepStatus, RouteSummary, build_service_registry, service_health_payload
from fortifylab.web import WebConsoleApp, WebConsoleConfig


ENV_TEXT = """
DOMAIN=lab.example
SSC=ssc.lab.example
LIM=lim.lab.example
SCDAST=dast.lab.example
SCSAST=sast.lab.example
SSC_URL=https://ssc.lab.example
LIM_URL=https://lim.lab.example
LIM_API_URL=https://lim.lab.example/LIM.API
SCDAST_URL=https://dast.lab.example
SCSAST_URL=https://sast.lab.example
SCSAST_CTRL_URL=https://sast.lab.example/scancentral-ctrl/
DEFAULT_PASS=do-not-leak
SSC_CITOKEN=secret-token
"""


class ServiceRegistryTests(unittest.TestCase):
    def test_registry_derives_services_from_env_without_secrets(self) -> None:
        registry = build_service_registry(env_text=ENV_TEXT)
        payload = registry.to_dict()

        self.assertEqual(payload["domain"], "lab.example")
        by_id = {service["service_id"]: service for service in payload["services"]}
        self.assertEqual(by_id["ssc"]["url"], "https://ssc.lab.example")
        self.assertEqual(by_id["dashboard"]["url"], "https://dashboard.lab.example")
        self.assertTrue(payload["secrets_redacted"])
        self.assertNotIn("do-not-leak", str(payload))
        self.assertNotIn("secret-token", str(payload))

    def test_registry_reports_url_config_drift(self) -> None:
        registry = build_service_registry(env_text=ENV_TEXT.replace("SSC_URL=https://ssc.lab.example", "SSC_URL=LIM_URL"))

        self.assertTrue(any("SSC_URL is set to placeholder-like value LIM_URL" in issue for issue in registry.config_issues))

    def test_health_payload_adds_dns_tls_http_and_ingress_hints(self) -> None:
        registry = build_service_registry(env_text=ENV_TEXT)
        payload = service_health_payload(registry, checker=FakeChecker(), snapshot=FakeStatusPoller().snapshot())
        by_id = {service["service_id"]: service for service in payload["services"]}

        self.assertEqual(by_id["ssc"]["checks"]["dns"]["state"], "ok")
        self.assertEqual(by_id["ssc"]["checks"]["ingress"]["state"], "ok")
        self.assertEqual(by_id["dast"]["checks"]["tls"]["state"], "blocked")
        self.assertTrue(any(hint["check"] == "tls" for hint in by_id["dast"]["hints"]))
        self.assertTrue(payload["secrets_redacted"])

    def test_web_api_exposes_registry_and_health_envelopes(self) -> None:
        app = WebConsoleApp(WebConsoleConfig(), status_poller=FakeStatusPoller(), url_health_checker=FakeChecker())

        status, registry = app.api_envelope("/api/services")
        self.assertEqual(status, 200)
        self.assertTrue(registry["ok"])
        self.assertIn("services", registry["data"])

        status, health = app.api_envelope("/api/services/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertIn("checks", health["data"]["services"][0])


class FakeChecker:
    def check(self, service):
        tls_state = "blocked" if service.service_id == "dast" else "ok"
        return {
            "service_id": service.service_id,
            "label": service.label,
            "url": service.url,
            "host": service.host,
            "checks": {
                "dns": {"state": "ok", "message": "DNS resolves."},
                "tls": {"state": tls_state, "message": "TLS failed." if tls_state == "blocked" else "TLS ok."},
                "http": {"state": "ok", "message": "HTTP returned 200.", "status_code": 200},
            },
            "hints": [],
        }


class FakeStatusPoller:
    def snapshot(self) -> LiveDeploymentSnapshot:
        return LiveDeploymentSnapshot(
            namespace="fortify",
            profile="full_lab",
            generated_at="2026-08-14T00:00:00+00:00",
            overall_state=LiveState.COMPLETE,
            steps=(
                LiveStepStatus(
                    "ssc",
                    "Software Security Center",
                    LiveState.COMPLETE,
                    "ready",
                    routes=(
                        RouteSummary("ssc.lab.example", True, tls_secret="ssc-tls", service_name="ssc-webapp", endpoints_ready=True),
                        RouteSummary("ssc.fortifydemo.com", True, tls_secret="ssc-tls", service_name="ssc-webapp", endpoints_ready=True),
                    ),
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
