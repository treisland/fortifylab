"""M9.8 dashboard access, URLs, and credentials workflow contract tests.

These tests are clone-safe: they use injected fixture config/state providers and
never invoke Kubernetes, Helm, Docker, network, credentials, or live lab
operations.
"""

from __future__ import annotations

from importlib import import_module
import unittest

from fortifylab.navigation import find_item
from fortifylab.status import ComponentStatus, LabStatus
from fortifylab.tui import workflows


FIXTURE_CONFIG = {
    "DOMAIN": "lab.example.test",
    "SSC_URL": "https://ssc.lab.example.test",
    "LIM_URL": "https://lim.lab.example.test",
    "LIM_API_URL": "https://lim.lab.example.test/LIM.API",
    "SCDAST_URL": "https://dast.lab.example.test",
    "SCSAST_URL": "https://sast.lab.example.test",
    "SCSAST_CTRL_URL": "https://sast.lab.example.test/scancentral-ctrl/",
    "JUICE_SHOP_URL": "https://juice-shop.lab.example.test",
    "DEFAULT_ALIAS": "admin",
    "DEFAULT_PASS": "plain-secret-password",
    "SCDAST_SSC_USER": "scdast-admin",
    "SCDAST_SSC_PASS": "scdast-secret",
    "LIM_POOL_NAME": "FortifyPool",
    "LIM_POOL_PASS": "lim-pool-secret",
    "FORTIFY_LICENSE_FILE": "/home/example/fortify.license",
}


def fixture_status() -> LabStatus:
    return LabStatus(
        "fortify",
        "fixture",
        (
            ComponentStatus("ssc", 1, 1, "ready"),
            ComponentStatus("lim", 1, 1, "ready"),
            ComponentStatus("scancentral-sast", 0, 1, "pending"),
            ComponentStatus("scancentral-dast", 0, 1, "pending"),
        ),
        ("fixture status only; no live cluster queried",),
    )


class M9DashboardAccessWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.contract = import_module("fortifylab.tui.dashboard_access")
        except ModuleNotFoundError as exc:
            if exc.name != "fortifylab.tui.dashboard_access":
                raise
            self.fail(
                "M9.8 requires fortifylab.tui.dashboard_access with "
                "DashboardAccessScreen, UrlsCredentialsScreen, "
                "build_dashboard_access_snapshot, build_urls_credentials_snapshot, "
                "and mask_secret."
            )

    def test_dashboard_snapshot_uses_fixture_config_and_status_without_live_dependencies(self) -> None:
        snapshot = self.contract.build_dashboard_access_snapshot(
            config_provider=lambda: FIXTURE_CONFIG,
            status_provider=fixture_status,
        )

        entries = {entry.id: entry for entry in snapshot.entries}
        self.assertEqual(snapshot.state, self.contract.AccessState.WARN)
        self.assertEqual(entries["ssc"].url, "https://ssc.lab.example.test")
        self.assertEqual(entries["ssc"].state, self.contract.AccessState.PASS)
        self.assertEqual(entries["scancentral_sast"].state, self.contract.AccessState.WARN)
        self.assertIn("no live cluster queried", " ".join(snapshot.notes))

        rendered = self.contract.DashboardAccessScreen(snapshot_provider=lambda: snapshot).render()
        self.assertIn("Dashboard access", rendered)
        self.assertIn("SSC", rendered)
        self.assertIn("https://ssc.lab.example.test", rendered)
        self.assertNotIn("plain-secret-password", rendered)

    def test_urls_credentials_snapshot_masks_secrets_and_keeps_public_urls_visible(self) -> None:
        snapshot = self.contract.build_urls_credentials_snapshot(
            config_provider=lambda: FIXTURE_CONFIG,
            status_provider=fixture_status,
        )

        values = {entry.key: entry.rendered_value for entry in snapshot.entries}
        self.assertEqual(values["SSC_URL"], "https://ssc.lab.example.test")
        self.assertEqual(values["DEFAULT_ALIAS"], "admin")
        self.assertEqual(values["DEFAULT_PASS"], "<redacted>")
        self.assertEqual(values["SCDAST_SSC_PASS"], "<redacted>")
        self.assertEqual(values["LIM_POOL_PASS"], "<redacted>")
        self.assertEqual(values["FORTIFY_LICENSE_FILE"], "<redacted>")
        rendered = self.contract.UrlsCredentialsScreen(snapshot_provider=lambda: snapshot).render()
        self.assertNotIn("plain-secret-password", rendered)
        self.assertNotIn("scdast-secret", rendered)

    def test_missing_values_produce_safe_states_and_recommended_handoffs(self) -> None:
        snapshot = self.contract.build_urls_credentials_snapshot(
            config_provider=lambda: {"DOMAIN": "lab.example.test"},
            status_provider=lambda: LabStatus("fortify", "clone-safe"),
        )

        entries = {entry.key: entry for entry in snapshot.entries}
        self.assertEqual(entries["SSC_URL"].state, self.contract.AccessState.WARN)
        self.assertEqual(entries["DEFAULT_PASS"].rendered_value, "<unset>")
        self.assertEqual(entries["DEFAULT_PASS"].state, self.contract.AccessState.WARN)
        self.assertTrue(
            {"configuration_editor", "diagnostics", "status", "help_center"}
            <= {action.workflow_target for action in snapshot.recommended_actions}
        )

    def test_workflow_dispatch_preserves_more_tools_targets(self) -> None:
        cases = (
            ("7", "dashboard_access", "Dashboard access"),
            ("13", "urls_credentials", "URLs and credentials"),
        )

        for key, screen_id, title in cases:
            with self.subTest(key=key):
                selected = find_item("more_tools", key)
                assert selected is not None

                result = workflows.dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertEqual(result.screen.id, screen_id)
                self.assertEqual(result.screen.title, title)

    def test_screens_support_arrow_number_refresh_back_and_recommended_handoffs(self) -> None:
        snapshot = self.contract.build_dashboard_access_snapshot(
            config_provider=lambda: FIXTURE_CONFIG,
            status_provider=fixture_status,
        )
        calls = {"count": 0}

        def provider():
            calls["count"] += 1
            return snapshot

        screen = self.contract.DashboardAccessScreen(snapshot_provider=provider)

        self.assertIn("Recommended actions:", screen.render())
        self.assertIn("Selected action", screen.handle_key("down").message)
        self.assertIn("Selected action", screen.handle_key("1").message)
        self.assertEqual(screen.handle_key("enter").open_target, "configuration_editor")
        self.assertEqual(screen.handle_key("r").message, "Refreshed dashboard access.")
        self.assertEqual(calls["count"], 2)
        self.assertTrue(screen.handle_key("b").exit_screen)

    def test_mask_secret_handles_empty_and_known_secret_shapes(self) -> None:
        self.assertEqual(self.contract.mask_secret("DEFAULT_PASS", ""), "<unset>")
        self.assertEqual(self.contract.mask_secret("DEFAULT_PASS", "fortify"), "<redacted>")
        self.assertEqual(
            self.contract.mask_secret("SSC_URL", "https://ssc.example.test"),
            "https://ssc.example.test",
        )


if __name__ == "__main__":
    unittest.main()
