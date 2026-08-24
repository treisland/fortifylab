"""Unit tests for GuidedDeployScreen (M3 of the TUI migration)."""

from __future__ import annotations

import sys
import time
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


def _wait_for_execution(screen: GuidedDeployScreen, *, timeout: float = 2.0) -> None:
    """Drive TickEvents until the background step started by ``enter``
    while armed (see DeployService.start_execute()) finishes -- real
    execution now runs off-thread precisely so the screen can show
    "running" instead of freezing (the bug this whole mechanism fixes)."""

    deadline = time.monotonic() + timeout
    while screen.service.is_executing:
        if time.monotonic() > deadline:
            raise AssertionError("background step did not finish within the test timeout")
        screen.handle_event(TickEvent(0.0))
        time.sleep(0.01)


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

    def test_completed_and_failed_steps_are_color_coded(self) -> None:
        # Bug report: every step's status rendered in plain, uncolored
        # text, matching neither Bash's guided_status_render() (which
        # colors complete=green, in_progress/pending=yellow, failed=red)
        # nor giving any visual cue for what's already done vs. still to
        # do. Use a color-enabled style (the real runtime default) and
        # check for the raw ANSI codes.
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("true",))
        object.__setattr__(service.plan.steps[1], "command", ("false",))
        screen = GuidedDeployScreen(style=TerminalStyle(color=True, symbols=True), service=service)

        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))  # certs: complete
        _wait_for_execution(screen)
        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))  # dashboard: fails
        _wait_for_execution(screen)

        rendered = screen.render()
        self.assertIn("[32m", rendered)  # green, complete
        self.assertIn("[31m", rendered)  # red, failed

    def test_enter_when_armed_starts_running_immediately(self) -> None:
        # The core fix for "no way to tell tasks are currently running":
        # a real execution must show as RUNNING on the very next render,
        # before the (possibly slow) command has finished -- not just
        # freeze until it returns.
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("sleep", "0.2"))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(service.states["certs"].status, StepStatus.RUNNING)
        self.assertTrue(service.is_executing)
        self.assertIn("running", screen.render())
        _wait_for_execution(screen)
        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)

    def test_enter_when_armed_executes_and_advances(self) -> None:
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("true",))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))
        _wait_for_execution(screen)

        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)
        self.assertIn("Operation completed", screen.render())

    def test_arming_auto_disarms_after_one_real_execution(self) -> None:
        # Security review finding: arming was session-sticky, so a stray
        # extra "enter" after arming would silently execute the *next*
        # step for real too. Arming must be a one-shot, per-step decision.
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("true",))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))
        self.assertFalse(screen.armed)
        _wait_for_execution(screen)
        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)

        # A follow-up "enter" without re-arming must stay a dry-run preview.
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(service.states["secrets"].status, StepStatus.PENDING)

    def test_enter_while_already_executing_does_not_start_a_second_step(self) -> None:
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("sleep", "0.2"))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(service.is_executing)
        # A stray extra "enter" (or arming again) while a step is still
        # running must be a no-op, not start a second background thread.
        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(service.states["dashboard"].status, StepStatus.PENDING)
        _wait_for_execution(screen)
        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)

    def test_disarming_without_executing_leaves_armed_state_unchanged(self) -> None:
        # Pressing "enter" while not armed is a dry-run preview and must not
        # touch the armed flag either way.
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        self.assertFalse(screen.armed)

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

    def test_o_on_every_menu_item_now_pushes_a_real_screen(self) -> None:
        # As of M12 (#446 slice 6, the Dashboard screen), every OPERATOR_MENU
        # item has a real screen wired -- there is no longer an item where
        # "o" is a no-op. This replaces the old "unwired item" regression
        # test, whose premise ("dashboard" had no screen) is no longer true.
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        for index, item in enumerate(menu.items):
            menu.selected_index = index
            command = menu.handle_event(KeyEvent("o"))
            self.assertEqual(command.kind, NavigationKind.PUSH, f"expected a real screen for '{item.key}'")

    def test_deploy_item_preview_hints_at_opening(self) -> None:
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        deploy_index = next(i for i, item in enumerate(menu.items) if item.key == "deploy")
        menu.selected_index = deploy_index
        menu.show_detail = True

        self.assertIn("press o to open", menu.render())


if __name__ == "__main__":
    unittest.main()
