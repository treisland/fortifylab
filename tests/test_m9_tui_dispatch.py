"""M9.1 tests for TUI workflow dispatch contracts."""

from __future__ import annotations

import unittest

from fortifylab.navigation import ActionKind, ActionRef, MenuItem, find_item
from fortifylab.tui.workflows import WorkflowScreen, dispatch_menu_item


class M9TuiDispatchTests(unittest.TestCase):
    def test_menu_action_opens_existing_menu(self) -> None:
        selected = find_item("main", "m")
        assert selected is not None

        result = dispatch_menu_item(selected)

        self.assertEqual(result.kind, "menu")
        self.assertIsNotNone(result.menu)
        assert result.menu is not None
        self.assertEqual(result.menu.id, "more_tools")
        self.assertEqual(result.message, "Opened More tools.")

    def test_help_and_runbook_actions_open_registered_workflow_screens(self) -> None:
        cases = (
            ("main", "?", "help_center", "Help Center"),
            ("more_tools", "15", "runbook_library", "Runbook Library"),
            ("more_tools", "17", "help_center", "Help Center"),
            ("more_tools", "18", "operational_guidance", "Operational guidance"),
        )

        for menu_id, key, screen_id, title in cases:
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None

                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertEqual(result.screen.id, screen_id)
                self.assertEqual(result.screen.title, title)
                self.assertIn("workflow boundary", result.screen.render())

    def test_registered_lifecycle_placeholder_action_opens_contract_screen(self) -> None:
        selected = find_item("lifecycle", "1")
        assert selected is not None

        result = dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsNone(result.menu)
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertIn("lab.start.all", result.screen.render())

    def test_registered_workflows_can_be_injected_for_future_screens(self) -> None:
        selected = MenuItem(
            "x",
            "Custom workflow",
            ActionRef(ActionKind.VIEW, "custom_workflow", placeholder=False),
        )

        result = dispatch_menu_item(
            selected,
            workflows={
                "custom_workflow": lambda _item: WorkflowScreen(
                    "custom_workflow",
                    "Custom workflow",
                    "Injected workflow screen.",
                )
            },
        )

        self.assertEqual(result.kind, "screen")
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertEqual(result.screen.render(), "Injected workflow screen.")

    def test_unknown_nonplaceholder_action_reports_modeled_later(self) -> None:
        selected = MenuItem(
            "x",
            "Modeled action",
            ActionRef(ActionKind.COMMAND, "future.command", placeholder=False),
        )

        result = dispatch_menu_item(selected)

        self.assertEqual(result.kind, "modeled")
        self.assertEqual(result.message, "Modeled action is modeled; operation wiring starts in a later milestone.")


if __name__ == "__main__":
    unittest.main()
