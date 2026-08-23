"""Unit tests for GuidedDeployScreen (M3 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.orchestration import OperationController, RetryPolicy, StepStatus  # noqa: E402
from fortifylab.services.deploy_service import DeployService  # noqa: E402
from fortifylab.tui.events import KeyEvent, TickEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.guided_deploy import GuidedDeployScreen  # noqa: E402
from fortifylab.tui.screens.main_menu import MainMenuScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _plain_screen() -> GuidedDeployScreen:
    return GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False))


class GuidedDeployScreenTests(unittest.TestCase):
    def test_renders_every_plan_step(self) -> None:
        screen = _plain_screen()
        rendered = screen.render()
        for step in screen.service.plan.steps:
            self.assertIn(step.label, rendered)

    def test_starts_in_dry_run_mode(self) -> None:
        screen = _plain_screen()
        self.assertFalse(screen.armed)
        self.assertIn("dry-run", screen.render())

    def test_a_toggles_armed_mode(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("a"))
        self.assertTrue(screen.armed)
        self.assertIn("EXECUTE", screen.render())
        screen.handle_event(KeyEvent("a"))
        self.assertFalse(screen.armed)

    def test_enter_in_dry_run_mode_previews_without_advancing(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        self.assertIsNotNone(screen.last_result)
        self.assertEqual(screen.service.states["certs"].status, StepStatus.PENDING)
        self.assertIn("not executed", screen.render())

    def test_enter_when_armed_executes_and_advances(self) -> None:
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("true",))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)
        self.assertIn("Operation completed", screen.render())

    def test_q_pops_back_to_the_previous_screen(self) -> None:
        screen = _plain_screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)

    def test_tick_event_is_counted_and_does_not_change_navigation(self) -> None:
        screen = _plain_screen()
        command = screen.handle_event(TickEvent(1.0))
        self.assertEqual(command.kind, NavigationKind.STAY)
        self.assertEqual(screen.ticks, 1)


class MainMenuOpensGuidedDeployTests(unittest.TestCase):
    def test_o_on_the_deploy_item_pushes_a_guided_deploy_screen(self) -> None:
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        deploy_index = next(i for i, item in enumerate(menu.items) if item.key == "deploy")
        menu.selected_index = deploy_index

        command = menu.handle_event(KeyEvent("o"))

        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, GuidedDeployScreen)

    def test_o_on_an_item_without_a_real_screen_does_nothing(self) -> None:
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        dashboard_index = next(i for i, item in enumerate(menu.items) if item.key == "dashboard")
        menu.selected_index = dashboard_index

        command = menu.handle_event(KeyEvent("o"))

        self.assertEqual(command.kind, NavigationKind.STAY)

    def test_deploy_item_preview_hints_at_opening(self) -> None:
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        deploy_index = next(i for i, item in enumerate(menu.items) if item.key == "deploy")
        menu.selected_index = deploy_index
        menu.show_detail = True

        self.assertIn("press o to open", menu.render())


if __name__ == "__main__":
    unittest.main()
