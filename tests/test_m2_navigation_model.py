"""M2 acceptance tests for the Python TUI navigation model."""

from __future__ import annotations

import unittest

from fortifylab.navigation import ActionKind, find_item, get_menu, menu_keys, menu_labels


class M2NavigationModelTests(unittest.TestCase):
    maxDiff = None

    def test_main_menu_preserves_baseline_labels_and_order(self) -> None:
        self.assertEqual(
            menu_keys("main"),
            ("0", "1", "2", "3", "4", "5", "?", "m", "q"),
        )
        self.assertEqual(
            menu_labels("main"),
            (
                "Initial setup and readiness",
                "Deploy: guided, express, resume",
                "Lab lifecycle controls",
                "Configuration editor",
                "Logs",
                "First-scan one-click demo",
                "Help Center / Fortify Knowledge Center",
                "More tools",
                "Quit",
            ),
        )

    def test_more_tools_preserves_compatibility_menu_order(self) -> None:
        self.assertEqual(
            menu_labels("more_tools"),
            (
                "Setup and readiness",
                "Guided deployment",
                "Express deployment",
                "Resume or repair",
                "Flight Plans",
                "App management",
                "Sample apps",
                "Dashboard access",
                "Diagnostics",
                "Advanced setup",
                "Lifecycle controls",
                "Logs",
                "Cluster snapshot",
                "URLs and credentials",
                "FCLI readiness",
                "Runbook Library",
                "Configuration editor",
                "Help Center",
                "Operational guidance",
                "Wizard log",
                "First-scan one-click demo",
                "Back",
                "Quit",
            ),
        )

    def test_disabled_items_carry_reasons(self) -> None:
        main_demo = find_item("main", "5")
        more_demo = find_item("more_tools", "20")

        self.assertIsNotNone(main_demo)
        self.assertIsNotNone(more_demo)
        self.assertFalse(main_demo.enabled)
        self.assertFalse(more_demo.enabled)
        self.assertIn("deploy SSC", main_demo.disabled_reason)
        self.assertEqual(main_demo.disabled_reason, more_demo.disabled_reason)

    def test_aliases_and_quit_are_distinct_from_return(self) -> None:
        main = get_menu("main")
        deploy = get_menu("deploy")
        back = find_item("deploy", "b")
        quit_item = find_item("deploy", "q")

        self.assertEqual(main.back_aliases, ("b", "escape", ""))
        self.assertEqual(deploy.return_aliases, ("r", ""))
        self.assertIsNotNone(back)
        self.assertTrue(back.matches("escape"))
        self.assertTrue(back.matches(""))
        self.assertEqual(back.action.kind, ActionKind.RETURN)
        self.assertIsNotNone(quit_item)
        self.assertEqual(quit_item.action.kind, ActionKind.QUIT)

    def test_duplicate_number_keys_are_scoped_by_menu_id(self) -> None:
        self.assertEqual(find_item("main", "1").action.target, "deploy")
        self.assertEqual(find_item("more_tools", "1").action.target, "guided_deployment")
        self.assertEqual(find_item("guided_deployment", "1").action.target, "guided_deployment.profile_selection")

    def test_number_keys_are_jump_highlight_until_activated(self) -> None:
        for menu_id in ("main", "more_tools", "guided_deployment"):
            with self.subTest(menu_id=menu_id):
                self.assertEqual(get_menu(menu_id).number_key_mode, "jump_highlight")

    def test_placeholder_targets_are_explicit_until_later_milestones(self) -> None:
        self.assertFalse(find_item("main", "1").action.placeholder)
        self.assertFalse(find_item("deploy", "1").action.placeholder)
        self.assertTrue(find_item("main", "3").action.placeholder)
        self.assertTrue(find_item("more_tools", "15").action.placeholder)
        self.assertEqual(find_item("app_lifecycle", "3").action.kind, ActionKind.PLACEHOLDER)
        self.assertTrue(find_item("app_lifecycle", "3").action.placeholder)

    def test_guided_deployment_is_a_workflow_boundary(self) -> None:
        guided = get_menu("guided_deployment")

        self.assertTrue(guided.workflow_boundary)
        self.assertEqual(
            menu_labels("guided_deployment")[:4],
            (
                "Profile selection",
                "Deployment mode selection",
                "Per-step controls",
                "Completion handoff",
            ),
        )
        for key in ("1", "2", "3", "4"):
            with self.subTest(key=key):
                self.assertEqual(find_item("guided_deployment", key).action.kind, ActionKind.PLACEHOLDER)


if __name__ == "__main__":
    unittest.main()
