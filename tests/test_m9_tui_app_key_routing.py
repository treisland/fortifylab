"""M9.4 clone-safe TUI app key routing tests."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from fortifylab.tui.app import workflow_key_from_event


@dataclass
class FakeKeyEvent:
    key: str
    character: str | None = None


class M9TuiAppKeyRoutingTests(unittest.TestCase):
    def test_printable_workflow_action_keys_are_forwardable(self) -> None:
        for character in ("p", "c", "y", "n", "?", "m"):
            with self.subTest(character=character):
                self.assertEqual(
                    workflow_key_from_event(FakeKeyEvent(key=character, character=character)),
                    character,
                )

    def test_digit_workflow_keys_are_forwardable_for_number_selection(self) -> None:
        self.assertEqual(workflow_key_from_event(FakeKeyEvent(key="2", character="2")), "2")

    def test_non_printable_keys_do_not_use_printable_workflow_route(self) -> None:
        self.assertIsNone(workflow_key_from_event(FakeKeyEvent(key="up", character=None)))
        self.assertIsNone(workflow_key_from_event(FakeKeyEvent(key="escape", character=None)))


if __name__ == "__main__":
    unittest.main()
