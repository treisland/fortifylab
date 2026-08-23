"""Unit tests for HelpScreen (M5 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.help import HelpScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _plain_screen() -> HelpScreen:
    return HelpScreen(style=TerminalStyle(color=False, symbols=False))


class HelpScreenTests(unittest.TestCase):
    def test_renders_every_topic(self) -> None:
        screen = _plain_screen()
        rendered = screen.render()
        for topic in screen.topics:
            self.assertIn(topic.label, rendered)

    def test_enter_views_the_selected_topic_with_real_content(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(screen.viewing)
        rendered = screen.render()
        self.assertIn("Help --", rendered)
        self.assertIsNotNone(screen.content)

    def test_b_returns_from_viewing_to_the_topic_list(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        screen.handle_event(KeyEvent("b"))
        self.assertFalse(screen.viewing)

    def test_missing_help_file_shows_an_error_not_a_crash(self) -> None:
        from fortifylab.domain.help_center import HelpTopic

        screen = HelpScreen(
            style=TerminalStyle(color=False, symbols=False),
            topics=(HelpTopic("nope", "Nonexistent", "does-not-exist.txt"),),
        )
        screen.handle_event(KeyEvent("enter"))
        self.assertIn("unavailable", screen.render())

    def test_navigation_wraps(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("up"))
        self.assertEqual(screen.selected_index, len(screen.topics) - 1)

    def test_q_pops_even_while_viewing(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
