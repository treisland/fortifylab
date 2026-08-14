"""Contracts for the companion web console."""

from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fortifylab.web import WebConsoleApp, WebConsoleConfig, build_http_server


class PythonWebConsoleTests(unittest.TestCase):
    def request_once(self, config: WebConsoleConfig, path: str, *, headers: dict[str, str] | None = None):
        server = build_http_server(config)
        host, port = server.server_address[:2]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            request = Request(f"http://{host}:{port}{path}", headers=headers or {})
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
        for expected in ('data-panel="deployment"', 'data-panel="configuration"', 'data-panel="routes"', 'data-panel="certificates"'):
            self.assertIn(expected, html)

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

    def test_api_endpoints_cover_status_config_routes_certificates(self) -> None:
        app = WebConsoleApp(WebConsoleConfig())

        for path in ("/api/status", "/api/config", "/api/routes", "/api/certificates", "/api/deployment/status"):
            with self.subTest(path=path):
                status, payload = app.api_envelope(path)
                self.assertEqual(status, 200)
                self.assertTrue(payload["ok"])
                self.assertIsNone(payload["error"])

    def test_deployment_status_api_returns_steps(self) -> None:
        status, payload = WebConsoleApp(WebConsoleConfig()).api_envelope("/api/deployment/status")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("steps", payload["data"])


if __name__ == "__main__":
    unittest.main()
