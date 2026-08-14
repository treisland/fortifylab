"""Phase 6 web action security contracts."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fortifylab.operations import ActionPreviewCatalog, OperationCatalog, redact_value  # noqa: E402
from fortifylab.web import WebConsoleApp, WebConsoleConfig  # noqa: E402


class Phase6ActionSecurityTests(unittest.TestCase):
    def test_web_console_is_read_only_by_default(self) -> None:
        status, payload = WebConsoleApp(WebConsoleConfig()).api_response("/api/status")

        self.assertEqual(status, 200)
        self.assertEqual(payload["security"]["mode"], "read_only")
        self.assertFalse(payload["security"]["enable_actions"])

    def test_action_catalog_exposes_allowlisted_previews_without_enabling_execution(self) -> None:
        status, payload = WebConsoleApp(WebConsoleConfig()).api_response("/api/actions")

        self.assertEqual(status, 200)
        actions = {action["id"]: action for action in payload["actions"]}
        self.assertIn("app.ssc.stop", actions)
        self.assertIn("logs.ssc-webapp-0", actions)
        self.assertFalse(actions["app.ssc.stop"]["execution_enabled"])
        self.assertEqual(actions["app.ssc.destroy"]["confirmation"]["phrase"], "DESTROY ssc")
        self.assertTrue(actions["app.ssc.destroy"]["confirmation"]["case_sensitive"])

    def test_enable_actions_config_only_marks_mutating_action_previews_executable(self) -> None:
        status, payload = WebConsoleApp(WebConsoleConfig(enable_actions=True)).api_response("/api/actions")

        self.assertEqual(status, 200)
        actions = {action["id"]: action for action in payload["actions"]}
        self.assertTrue(actions["app.ssc.stop"]["execution_enabled"])
        self.assertFalse(actions["logs.ssc-webapp-0"]["execution_enabled"])

    def test_unknown_action_preview_is_not_cataloged(self) -> None:
        status, payload = WebConsoleApp(WebConsoleConfig()).api_response("/api/actions/../../secrets")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "action not found")

    def test_preview_redacts_secret_like_command_parts(self) -> None:
        catalog = OperationCatalog()
        preview_catalog = ActionPreviewCatalog(catalog, enable_actions=True)
        value = redact_value({"command": ("tool", "token=abc123", "password=swordfish")})

        self.assertEqual(value["command"][1], "token=<redacted>")
        self.assertEqual(value["command"][2], "password=<redacted>")
        self.assertIsNotNone(preview_catalog.get("secrets.create"))


if __name__ == "__main__":
    unittest.main()
