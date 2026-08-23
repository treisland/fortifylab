"""Unit tests for the M2 TUI framework: router, screen stack, main menu."""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent, ResizeEvent, TickEvent  # noqa: E402
from fortifylab.tui.menu import OPERATOR_MENU  # noqa: E402
from fortifylab.tui.router import Router  # noqa: E402
from fortifylab.tui.screens.base import NavigationCommand, NavigationKind, Screen  # noqa: E402
from fortifylab.tui.screens.main_menu import MainMenuScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


@dataclass
class _RecordingScreen(Screen):
    """Minimal screen double for router tests, independent of MainMenuScreen."""

    entered: list[str] = field(default_factory=list)
    exited: list[str] = field(default_factory=list)
    next_command: NavigationCommand = field(default_factory=NavigationCommand.stay)

    def render(self) -> str:
        return "recording-screen"

    def handle_event(self, event) -> NavigationCommand:  # noqa: ANN001
        return self.next_command

    def on_enter(self) -> None:
        self.entered.append("entered")

    def on_exit(self) -> None:
        self.exited.append("exited")


class MainMenuScreenTests(unittest.TestCase):
    def _screen(self) -> MainMenuScreen:
        return MainMenuScreen(style=TerminalStyle(color=False, symbols=False))

    def test_renders_every_operator_menu_item(self) -> None:
        screen = self._screen()
        rendered = screen.render()
        for item in OPERATOR_MENU:
            self.assertIn(item.label, rendered)

    def test_down_then_up_returns_to_the_first_item(self) -> None:
        screen = self._screen()
        screen.handle_event(KeyEvent("down"))
        self.assertEqual(screen.selected_index, 1)
        screen.handle_event(KeyEvent("up"))
        self.assertEqual(screen.selected_index, 0)

    def test_selection_wraps_at_both_ends(self) -> None:
        screen = self._screen()
        screen.handle_event(KeyEvent("up"))
        self.assertEqual(screen.selected_index, len(OPERATOR_MENU) - 1)
        screen.handle_event(KeyEvent("down"))
        self.assertEqual(screen.selected_index, 0)

    def test_enter_toggles_a_preview_of_the_selected_item(self) -> None:
        screen = self._screen()
        self.assertFalse(screen.show_detail)
        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(screen.show_detail)
        self.assertIn("Preview:", screen.render())
        screen.handle_event(KeyEvent("enter"))
        self.assertFalse(screen.show_detail)

    def test_digit_key_jumps_directly_to_that_item_and_previews_it(self) -> None:
        screen = self._screen()
        screen.handle_event(KeyEvent("3"))
        self.assertEqual(screen.selected_index, 2)
        self.assertTrue(screen.show_detail)

    def test_question_mark_jumps_to_help(self) -> None:
        screen = self._screen()
        screen.handle_event(KeyEvent("?"))
        help_index = next(i for i, item in enumerate(OPERATOR_MENU) if item.key == "help")
        self.assertEqual(screen.selected_index, help_index)
        self.assertTrue(screen.show_detail)

    def test_q_requests_quit(self) -> None:
        screen = self._screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.QUIT)

    def test_non_key_events_are_ignored(self) -> None:
        screen = self._screen()
        command = screen.handle_event(TickEvent(1.0))
        self.assertEqual(command.kind, NavigationKind.STAY)
        command = screen.handle_event(ResizeEvent(80, 24))
        self.assertEqual(command.kind, NavigationKind.STAY)


class RouterTests(unittest.TestCase):
    def test_initial_screen_receives_on_enter(self) -> None:
        screen = _RecordingScreen()
        Router(screen)
        self.assertEqual(screen.entered, ["entered"])

    def test_push_grows_the_stack_and_current_reflects_the_top(self) -> None:
        first = _RecordingScreen(next_command=NavigationCommand.stay())
        router = Router(first)
        second = _RecordingScreen()
        first.next_command = NavigationCommand.push(second)
        self.assertTrue(router.dispatch(KeyEvent("x")))
        self.assertIs(router.current, second)
        self.assertEqual(second.entered, ["entered"])

    def test_pop_returns_to_the_previous_screen_and_calls_on_exit(self) -> None:
        first = _RecordingScreen()
        router = Router(first)
        second = _RecordingScreen(next_command=NavigationCommand.pop())
        router.stack.append(second)
        self.assertTrue(router.dispatch(KeyEvent("x")))
        self.assertIs(router.current, first)
        self.assertEqual(second.exited, ["exited"])

    def test_quit_empties_the_stack_and_dispatch_reports_stopped(self) -> None:
        screen = _RecordingScreen(next_command=NavigationCommand.quit())
        router = Router(screen)
        self.assertFalse(router.dispatch(KeyEvent("q")))
        self.assertEqual(router.stack, [])

    def test_replace_swaps_the_current_screen_without_growing_the_stack(self) -> None:
        first = _RecordingScreen()
        router = Router(first)
        second = _RecordingScreen()
        first.next_command = NavigationCommand.replace(second)
        router.dispatch(KeyEvent("x"))
        self.assertEqual(len(router.stack), 1)
        self.assertIs(router.current, second)


if __name__ == "__main__":
    unittest.main()
