"""Unit tests for raw keypress parsing in fortifylab.tui.input.

These exercise TerminalInput.read_event() over a real pipe (selectable,
unlike a StringIO) without needing a real TTY, so they don't touch termios
raw-mode setup (which does require a TTY and is left to manual/interactive
testing).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.input import TerminalInput  # noqa: E402


class TerminalInputReadEventTests(unittest.TestCase):
    def setUp(self) -> None:
        read_fd, write_fd = os.pipe()
        self.write_fd = write_fd
        self.reader = os.fdopen(read_fd, "r")
        self.input = TerminalInput(self.reader)

    def tearDown(self) -> None:
        self.reader.close()
        os.close(self.write_fd)

    def _send(self, text: str) -> None:
        os.write(self.write_fd, text.encode())

    def test_plain_character(self) -> None:
        self._send("a")
        event = self.input.read_event(timeout=1)
        self.assertEqual(event.key, "a")

    def test_enter_normalizes_carriage_return(self) -> None:
        self._send("\r")
        event = self.input.read_event(timeout=1)
        self.assertEqual(event.key, "enter")

    def test_arrow_up_escape_sequence(self) -> None:
        self._send("\x1b[A")
        event = self.input.read_event(timeout=1)
        self.assertEqual(event.key, "up")

    def test_arrow_down_escape_sequence(self) -> None:
        self._send("\x1b[B")
        event = self.input.read_event(timeout=1)
        self.assertEqual(event.key, "down")

    def test_bare_escape_with_no_follow_up_is_escape(self) -> None:
        self._send("\x1b")
        event = self.input.read_event(timeout=1)
        self.assertEqual(event.key, "escape")

    def test_multibyte_utf8_character_decodes_correctly(self) -> None:
        self._send("é")
        event = self.input.read_event(timeout=1)
        self.assertEqual(event.key, "é")

    def test_timeout_with_no_input_returns_none(self) -> None:
        event = self.input.read_event(timeout=0.05)
        self.assertIsNone(event)

    def test_enter_requires_a_real_tty(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.input:
                pass


if __name__ == "__main__":
    unittest.main()
