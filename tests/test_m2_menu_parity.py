"""M2 contract tests for Python TUI menu parity.

These tests are intentionally noninteractive. They define the navigation model
and key-handling contracts expected by the TUI implementation without requiring
a terminal, Kubernetes, Helm, Docker, or network access.
"""

from __future__ import annotations

import importlib
import unittest
from typing import Any


navigation = importlib.import_module("fortifylab.navigation")
try:
    key_controller = importlib.import_module("fortifylab.navigation.controller")
except ModuleNotFoundError:
    key_controller = None


MODEL_DEPENDENCY = (
    "M2 menu parity contract depends on the deterministic navigation model from "
    "agent/navigation-M2-menu-model."
)
CONTROLLER_DEPENDENCY = (
    "M2 key handling contract depends on fortifylab.navigation.controller from "
    "agent/tui-M2-keybindings or a coordinated navigation helper."
)


REQUIRED_MODEL_SYMBOLS = (
    "ActionKind",
    "find_item",
    "get_menu",
    "menu_keys",
    "menu_labels",
)
HAS_NAVIGATION_MODEL = all(hasattr(navigation, name) for name in REQUIRED_MODEL_SYMBOLS)
HAS_CONTROLLER = key_controller is not None and all(
    hasattr(key_controller, name) for name in ("MenuController", "normalize_menu_key")
)


def value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def action_kind(item: Any) -> str:
    action = value(item, "action")
    kind = value(action, "kind", value(item, "action_type"))
    return str(value(kind, "value", kind))


@unittest.skipUnless(HAS_NAVIGATION_MODEL, MODEL_DEPENDENCY)
class M2MenuParityTests(unittest.TestCase):
    maxDiff = None

    def test_main_menu_matches_documented_bash_baseline(self) -> None:
        self.assertEqual(
            navigation.menu_keys("main"),
            ("0", "1", "2", "3", "4", "5", "?", "m", "q"),
        )
        self.assertEqual(
            navigation.menu_labels("main"),
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
        self.assertEqual(
            tuple(action_kind(navigation.find_item("main", key)) for key in navigation.menu_keys("main")),
            ("workflow", "menu", "menu", "view", "view", "workflow", "view", "menu", "quit"),
        )

    def test_more_tools_menu_preserves_compatibility_labels_and_numbering(self) -> None:
        self.assertEqual(
            navigation.menu_keys("more_tools"),
            tuple(str(i) for i in range(0, 21)) + ("b", "q"),
        )
        self.assertEqual(
            navigation.menu_labels("more_tools"),
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

    def test_disabled_items_expose_reason_text(self) -> None:
        main_demo = navigation.find_item("main", "5")
        more_demo = navigation.find_item("more_tools", "20")

        self.assertIsNotNone(main_demo)
        self.assertIsNotNone(more_demo)
        self.assertIs(value(main_demo, "enabled"), False)
        self.assertIs(value(more_demo, "enabled"), False)
        self.assertIsInstance(value(main_demo, "disabled_reason"), str)
        self.assertGreater(len(value(main_demo, "disabled_reason").strip()), 0)
        self.assertEqual(value(main_demo, "disabled_reason"), value(more_demo, "disabled_reason"))

    def test_return_and_quit_controls_are_distinct_and_aliasable(self) -> None:
        main = navigation.get_menu("main")
        deploy = navigation.get_menu("deploy")
        back = navigation.find_item("deploy", "b")
        quit_item = navigation.find_item("deploy", "q")

        self.assertIn("b", value(main, "back_aliases"))
        self.assertIn("escape", value(main, "back_aliases"))
        self.assertIn("r", value(deploy, "return_aliases"))
        self.assertTrue(back.matches("r"))
        self.assertTrue(back.matches("escape"))
        self.assertEqual(action_kind(back), "return")
        self.assertEqual(action_kind(quit_item), "quit")

    def test_number_keys_are_documented_as_jump_highlight(self) -> None:
        for menu_id in ("main", "more_tools", "guided_deployment"):
            with self.subTest(menu_id=menu_id):
                self.assertEqual(value(navigation.get_menu(menu_id), "number_key_mode"), "jump_highlight")


@unittest.skipUnless(HAS_NAVIGATION_MODEL and HAS_CONTROLLER, CONTROLLER_DEPENDENCY)
class M2KeyHandlingTests(unittest.TestCase):
    def test_number_keys_jump_to_item_without_activating_until_enter(self) -> None:
        controller = key_controller.MenuController(navigation.get_menu("main"))

        result = controller.handle_key("3")
        self.assertEqual(value(value(controller, "selected_item"), "key"), "3")
        self.assertEqual(value(result, "kind"), "select")
        self.assertIsNone(value(result, "activated_item"))

        result = controller.handle_key("enter")
        self.assertEqual(value(result, "kind"), "activate")
        self.assertEqual(value(value(result, "activated_item"), "key"), "3")

    def test_arrow_keys_move_selection_without_terminal_input(self) -> None:
        controller = key_controller.MenuController(navigation.get_menu("main"))

        self.assertEqual(value(value(controller, "selected_item"), "key"), "0")
        down = controller.handle_key("down")
        self.assertEqual(value(down, "kind"), "select")
        self.assertEqual(value(value(controller, "selected_item"), "key"), "1")
        up = controller.handle_key("up")
        self.assertEqual(value(up, "kind"), "select")
        self.assertEqual(value(value(controller, "selected_item"), "key"), "0")

    def test_back_help_and_quit_keys_are_normalized(self) -> None:
        expected = {
            "r": "back",
            "b": "back",
            "escape": "back",
            "esc": "back",
            "?": "help",
            "h": "help",
            "help": "help",
            "q": "quit",
            "ctrl+c": "quit",
            "enter": "enter",
            "return": "enter",
            "up": "up",
            "down": "down",
            "7": "7",
        }

        actual = {raw: key_controller.normalize_menu_key(raw) for raw in expected}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
