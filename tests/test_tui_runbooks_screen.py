"""Unit tests for RunbooksScreen (M5 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.runbooks import RunbooksScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _plain_screen() -> RunbooksScreen:
    return RunbooksScreen(style=TerminalStyle(color=False, symbols=False))


class RunbooksScreenTests(unittest.TestCase):
    def test_renders_every_topic(self) -> None:
        screen = _plain_screen()
        rendered = screen.render()
        for _topic_id, label in screen.topics:
            self.assertIn(label, rendered)

    def test_enter_previews_without_needing_to_arm(self) -> None:
        # Runbook previews are read-only; there is no arm concept here at all.
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(screen.viewing)
        self.assertIsNotNone(screen.last_execution)
        self.assertTrue(screen.last_execution.executed)

    def test_b_returns_to_the_topic_list(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        screen.handle_event(KeyEvent("b"))
        self.assertFalse(screen.viewing)

    def test_navigation_wraps(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("up"))
        self.assertEqual(screen.selected_index, len(screen.topics) - 1)

    def test_q_pops(self) -> None:
        screen = _plain_screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
