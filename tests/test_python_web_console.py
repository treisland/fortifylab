"""Contracts for the Phase 3.7 companion web console."""

from __future__ import annotations

import unittest

from fortifylab.web import WebConsoleApp, WebConsoleConfig


class PythonWebConsoleTests(unittest.TestCase):
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
        for expected in ("Deployment", "Logs", "Configuration", "Certificates"):
            self.assertIn(expected, html)


if __name__ == "__main__":
    unittest.main()
