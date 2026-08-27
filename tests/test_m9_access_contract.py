"""M9.8 dashboard access and URL/credential workflow contract tests.

These tests stay clone-safe: they use fixture providers only and do not touch
Kubernetes, Helm, Docker, network, live lab state, or real credentials.
"""

from __future__ import annotations

import unittest

from fortifylab.navigation import find_item
from fortifylab.tui import workflows
from fortifylab.tui.access import (
    AccessEntryState,
    ValueVisibility,
    build_access_snapshot,
    build_dashboard_access_workflow,
    build_urls_credentials_workflow,
)


FIXTURE_VALUES = {
    "DOMAIN": "demo.internal",
    "SSC": "ssc.$DOMAIN",
    "LIM": "lim.$DOMAIN",
    "SCDAST": "dast.$DOMAIN",
    "SCSAST": "sast.$DOMAIN",
    "SSC_URL": "https://$SSC",
    "LIM_URL": "https://$LIM",
    "LIM_API_URL": "https://$LIM/LIM.API",
    "SCDAST_URL": "https://$SCDAST",
    "SCSAST_URL": "https://$SCSAST",
    "SCSAST_CTRL_URL": "https://$SCSAST/scancentral-ctrl/",
    "DEFAULT_PASS": "super-secret-password",
    "DEFAULT_ALIAS": "admin",
    "SCDAST_SSC_USER": "dast-user",
    "SCDAST_SSC_PASS": "another-secret",
    "FORTIFY_LICENSE_FILE": "/sensitive/local/fortify.license",
}


class M9AccessContractTests(unittest.TestCase):
    def test_snapshot_derives_dashboard_and_expands_config_urls(self) -> None:
        snapshot = build_access_snapshot(env_values_provider=lambda: FIXTURE_VALUES)
        urls = {entry.key: entry for entry in snapshot.urls}

        self.assertEqual(urls["dashboard"].value, "https://dashboard.demo.internal")
        self.assertEqual(urls["SSC_URL"].value, "https://ssc.demo.internal")
        self.assertEqual(urls["SCSAST_CTRL_URL"].value, "https://sast.demo.internal/scancentral-ctrl/")
        self.assertEqual(urls["dashboard"].state, AccessEntryState.PRESENT)

    def test_credentials_are_masked_by_default_and_reveal_is_disabled(self) -> None:
        snapshot = build_access_snapshot(env_values_provider=lambda: FIXTURE_VALUES)
        credentials = {entry.key: entry for entry in snapshot.credentials}
        rendered = build_urls_credentials_workflow(snapshot_provider=lambda: snapshot).render()

        self.assertEqual(credentials["DEFAULT_PASS"].value, "<redacted>")
        self.assertEqual(credentials["DEFAULT_PASS"].visibility, ValueVisibility.MASKED)
        self.assertFalse(credentials["DEFAULT_PASS"].reveal_supported)
        self.assertEqual(credentials["DEFAULT_ALIAS"].value, "admin")
        self.assertNotIn("super-secret-password", rendered)
        self.assertNotIn("/sensitive/local/fortify.license", rendered)

    def test_missing_env_values_are_safe_missing_states(self) -> None:
        snapshot = build_access_snapshot(env_values_provider=lambda: {})
        urls = {entry.key: entry for entry in snapshot.urls}
        credentials = {entry.key: entry for entry in snapshot.credentials}

        self.assertTrue(snapshot.has_missing_values)
        self.assertEqual(urls["dashboard"].state, AccessEntryState.MISSING)
        self.assertEqual(credentials["DEFAULT_PASS"].state, AccessEntryState.MISSING)
        self.assertEqual(credentials["FORTIFY_LICENSE_FILE"].visibility, ValueVisibility.UNSET)

    def test_dashboard_tokens_are_unavailable_not_revealed_or_generated(self) -> None:
        snapshot = build_access_snapshot(env_values_provider=lambda: FIXTURE_VALUES)
        token_entries = {entry.key: entry for entry in snapshot.credentials if entry.key.startswith("dashboard.")}

        self.assertEqual(token_entries["dashboard.viewer.token"].state, AccessEntryState.SKIP)
        self.assertEqual(token_entries["dashboard.viewer.token"].visibility, ValueVisibility.UNAVAILABLE)
        self.assertFalse(token_entries["dashboard.admin.token"].reveal_supported)

    def test_dashboard_and_urls_menu_items_open_workflow_screens(self) -> None:
        dashboard_item = find_item("more_tools", "7")
        urls_item = find_item("more_tools", "13")
        assert dashboard_item is not None
        assert urls_item is not None

        dashboard_result = workflows.dispatch_menu_item(dashboard_item)
        urls_result = workflows.dispatch_menu_item(urls_item)

        self.assertEqual(dashboard_result.kind, "screen")
        self.assertEqual(urls_result.kind, "screen")
        assert dashboard_result.screen is not None
        assert urls_result.screen is not None
        self.assertEqual(dashboard_result.screen.id, "dashboard_access")
        self.assertEqual(urls_result.screen.id, "urls_credentials")

    def test_screen_supports_refresh_back_selection_and_handoff_contract(self) -> None:
        screen = build_dashboard_access_workflow(snapshot_provider=lambda: build_access_snapshot(env_values_provider=lambda: FIXTURE_VALUES))

        self.assertIn("Kubernetes Dashboard", screen.render())
        self.assertEqual(screen.handle_key("2").message, "Selected action 2: Open Status.")
        handoff = screen.handle_key("enter")
        self.assertEqual(handoff.open_target, "status")
        self.assertEqual(screen.handle_key("r").message, "Refreshed dashboard access.")
        self.assertEqual(screen.handle_key("down").message, "Selected action: next access handoff.")
        self.assertTrue(screen.handle_key("b").exit_screen)


if __name__ == "__main__":
    unittest.main()
