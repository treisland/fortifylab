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


def _wait_for_auto_advance(screen: GuidedDeployScreen, *, timeout: float = 2.0) -> None:
    """Like ``_wait_for_execution``, but drives through however many
    steps auto-advance chains while ``screen.armed`` stays True -- each
    finished step's TickEvent immediately starts the next runnable one,
    so this must keep polling until the whole run stops advancing
    (complete, failed, or disarmed), not just until one background
    thread finishes."""

    deadline = time.monotonic() + timeout
    while screen.service.is_executing or (screen.armed and not screen.service.is_complete and not screen.service.has_failed):
        if time.monotonic() > deadline:
            raise AssertionError("auto-advance did not finish within the test timeout")
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

    def test_running_step_is_colored_differently_from_pending_steps(self) -> None:
        # Regression test (bug report): RUNNING used to share PENDING's
        # color (warn/yellow), so a step that had actually started looked
        # the same shade as every step still waiting behind it -- read as
        # "is this stuck?". RUNNING must render with its own color.
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("sleep", "0.2"))
        screen = GuidedDeployScreen(style=TerminalStyle(color=True, symbols=True), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))

        rendered = screen.render()
        self.assertIn("[36m", rendered)  # cyan, running
        self.assertIn("[33m", rendered)  # yellow, still-pending steps
        _wait_for_execution(screen)

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
        # Disarm before waiting: only steps[0] has a safe, fake command --
        # armed staying True after it completes would auto-advance into
        # steps[1]'s real (unpatched) script next, which this test isn't
        # set up for. Auto-advance itself is covered by
        # test_arming_stays_on_and_auto_advances_through_every_step.
        screen.armed = False
        _wait_for_execution(screen)

        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)
        self.assertIn("Operation completed", screen.render())

    def test_arming_stays_on_and_auto_advances_through_every_step(self) -> None:
        # Bug report ("why not automatic"): Bash's own guided auto-advance
        # runs the whole remaining plan unattended after one confirmation,
        # stopping only for a failure -- arming one step and needing to
        # re-arm before every single subsequent step (the original,
        # stricter posture here) read as the deploy being stuck.
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        for step in service.plan.steps:
            object.__setattr__(step, "command", ("true",))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))
        _wait_for_auto_advance(screen)

        self.assertTrue(screen.armed)
        self.assertTrue(service.is_complete)
        for step in service.plan.steps:
            self.assertEqual(service.states[step.step_id].status, StepStatus.COMPLETE)

    def test_a_failed_step_auto_disarms_and_stops_the_auto_advance(self) -> None:
        # Matches Bash's own auto-advance: "stopping only for required
        # manual input or a failure" -- a failed step must not silently
        # let the next one start.
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("false",))
        object.__setattr__(service.plan.steps[1], "command", ("true",))
        screen = GuidedDeployScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=True)

        screen.handle_event(KeyEvent("enter"))
        _wait_for_auto_advance(screen)

        self.assertFalse(screen.armed)
        self.assertEqual(service.states[service.plan.steps[0].step_id].status, StepStatus.FAILED)
        self.assertEqual(service.states[service.plan.steps[1].step_id].status, StepStatus.PENDING)

        # A follow-up "enter" without re-arming stays a dry-run preview.
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(service.states[service.plan.steps[1].step_id].status, StepStatus.PENDING)

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
