"""Unit tests for LogsScreen (M4 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.operations import OperationRunner  # noqa: E402
from fortifylab.services.logs_service import LogsService  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.logs import LogsScreen, _Stage  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _runner_returning(text: str) -> OperationRunner:
    def fake_runner(command: tuple[str, ...]) -> CommandResult:
        return CommandResult(args=command, returncode=0, stdout=text, stderr="", duration_seconds=0.0)

    return OperationRunner(fake_runner)


class LogsScreenTests(unittest.TestCase):
    def test_starts_on_the_scopes_stage(self) -> None:
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False))
        self.assertEqual(screen.stage, _Stage.SCOPES)
        self.assertIn("Choose a component", screen.render())

    def test_single_matching_pod_skips_straight_to_output(self) -> None:
        service = LogsService(pod_lister=lambda: ("ssc-webapp-0",), runner=_runner_returning("log output\n"))
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False), service=service)
        ssc_index = next(i for i, (step_id, _l, _p) in enumerate(screen.scopes) if step_id == "ssc")
        screen.selected_scope_index = ssc_index

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.OUTPUT)
        self.assertIn("log output", screen.render())

    def test_multiple_matching_pods_show_a_selection_list(self) -> None:
        service = LogsService(
            pod_lister=lambda: ("ssc-webapp-0", "ssc-webapp-1"),
            runner=_runner_returning("log output\n"),
        )
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False), service=service)
        ssc_index = next(i for i, (step_id, _l, _p) in enumerate(screen.scopes) if step_id == "ssc")
        screen.selected_scope_index = ssc_index

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.PODS)
        self.assertEqual(screen.pods, ("ssc-webapp-0", "ssc-webapp-1"))
        rendered = screen.render()
        self.assertIn("ssc-webapp-0", rendered)
        self.assertIn("ssc-webapp-1", rendered)

        screen.handle_event(KeyEvent("down"))
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(screen.stage, _Stage.OUTPUT)
        self.assertEqual(screen.selected_pod_index, 1)

    def test_sast_sensor_scope_excludes_the_controller_pod(self) -> None:
        # scancentral-sast-controller-0 also starts with sast_sensor's
        # stripped prefix "scancentral-sast" -- the sensor scope must not
        # pull in the controller's pod (or worse, auto-tail it if it's
        # the only pod up so far).
        service = LogsService(
            pod_lister=lambda: ("scancentral-sast-controller-0", "scancentral-sast-sensor-0"),
            runner=_runner_returning("log output\n"),
        )
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False), service=service)
        sensor_index = next(i for i, (step_id, _l, _p) in enumerate(screen.scopes) if step_id == "sast_sensor")
        screen.selected_scope_index = sensor_index

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.OUTPUT)
        self.assertEqual(screen.pods, ("scancentral-sast-sensor-0",))

    def test_sast_controller_scope_is_unaffected_by_the_sensor_overlap(self) -> None:
        service = LogsService(
            pod_lister=lambda: ("scancentral-sast-controller-0", "scancentral-sast-sensor-0"),
            runner=_runner_returning("log output\n"),
        )
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False), service=service)
        controller_index = next(
            i for i, (step_id, _l, _p) in enumerate(screen.scopes) if step_id == "sast_controller"
        )
        screen.selected_scope_index = controller_index

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.OUTPUT)
        self.assertEqual(screen.pods, ("scancentral-sast-controller-0",))

    def test_no_matching_pods_shows_a_message_and_stays_on_scopes(self) -> None:
        service = LogsService(pod_lister=lambda: ())
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False), service=service)

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.SCOPES)
        self.assertIsNotNone(screen.message)

    def test_b_from_output_returns_to_pods_when_there_were_choices(self) -> None:
        service = LogsService(
            pod_lister=lambda: ("ssc-webapp-0", "ssc-webapp-1"),
            runner=_runner_returning("log output\n"),
        )
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False), service=service)
        ssc_index = next(i for i, (step_id, _l, _p) in enumerate(screen.scopes) if step_id == "ssc")
        screen.selected_scope_index = ssc_index
        screen.handle_event(KeyEvent("enter"))  # -> PODS
        screen.handle_event(KeyEvent("enter"))  # -> OUTPUT

        screen.handle_event(KeyEvent("b"))

        self.assertEqual(screen.stage, _Stage.PODS)

    def test_q_pops_from_any_stage(self) -> None:
        screen = LogsScreen(style=TerminalStyle(color=False, symbols=False))
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
