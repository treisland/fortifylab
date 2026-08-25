"""Unit tests for fortifylab.tui.widgets.TextField -- the reusable
text-entry widget that unblocks every typed-confirmation gap in the
migration (destroy, REVEAL, PERSISTENT, free-text .env edits)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent, TickEvent  # noqa: E402
from fortifylab.tui.widgets import TextField  # noqa: E402


class TextFieldTests(unittest.TestCase):
    def test_starts_empty(self) -> None:
        self.assertEqual(TextField().value, "")

    def test_printable_characters_append_to_the_buffer(self) -> None:
        field = TextField()
        for char in "DESTROY ssc":
            field.handle_key(KeyEvent(char))
        self.assertEqual(field.value, "DESTROY ssc")

    def test_backspace_removes_the_last_character(self) -> None:
        field = TextField(value="abc")
        field.handle_key(KeyEvent("backspace"))
        self.assertEqual(field.value, "ab")

    def test_backspace_on_empty_buffer_is_a_no_op(self) -> None:
        field = TextField()
        field.handle_key(KeyEvent("backspace"))
        self.assertEqual(field.value, "")

    def test_enter_and_escape_are_not_consumed(self) -> None:
        field = TextField()
        self.assertFalse(field.handle_key(KeyEvent("enter")))
        self.assertFalse(field.handle_key(KeyEvent("escape")))
        self.assertEqual(field.value, "")

    def test_navigation_keys_are_not_consumed(self) -> None:
        field = TextField()
        for key in ("up", "down", "left", "right", "ctrl-c"):
            self.assertFalse(field.handle_key(KeyEvent(key)))
        self.assertEqual(field.value, "")

    def test_non_key_events_are_ignored(self) -> None:
        field = TextField()
        self.assertFalse(field.handle_key(TickEvent(0.0)))

    def test_handle_key_reports_whether_it_consumed_the_event(self) -> None:
        field = TextField()
        self.assertTrue(field.handle_key(KeyEvent("D")))
        self.assertFalse(field.handle_key(KeyEvent("enter")))

    def test_max_length_stops_further_appends(self) -> None:
        field = TextField(max_length=3)
        for char in "abcdef":
            field.handle_key(KeyEvent(char))
        self.assertEqual(field.value, "abc")

    def test_clear_empties_the_buffer(self) -> None:
        field = TextField(value="something")
        field.clear()
        self.assertEqual(field.value, "")

    def test_render_shows_the_buffer_with_a_cursor(self) -> None:
        field = TextField(value="DESTROY ssc")
        self.assertEqual(field.render(), "DESTROY ssc_")


if __name__ == "__main__":
    unittest.main()
