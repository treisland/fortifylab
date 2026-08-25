"""Contracts for the Phase 3.2 guided deployment TUI prototype."""

from __future__ import annotations

import io
import unittest

from fortifylab.tui import ControlMode, GuidedStep, StepSnapshot, StepState, build_demo_snapshot, render_guided_step
from fortifylab.tui.screen import TerminalScreen


class GuidedTuiPrototypeTests(unittest.TestCase):
    def test_rendered_step_includes_expected_wait_controls(self) -> None:
        rendered = render_guided_step(build_demo_snapshot())

        self.assertIn("Guided deployment - Step 9 of 13", rendered)
        self.assertIn("State:   in progress", rendered)
        self.assertIn("Probe:   ssc_ready", rendered)
        self.assertIn("p. Pod logs", rendered)
        self.assertIn("Press i for interactive control", rendered)

    def test_complete_auto_advance_uses_five_second_countdown(self) -> None:
        snapshot = StepSnapshot(
            step=GuidedStep("mysql", "Verifying MySQL", "Waiting for MySQL.", log_scope="mysql*"),
            index=7,
            total=13,
            state=StepState.COMPLETE,
            detail="MySQL verified ready.",
            mode=ControlMode.AUTO_ADVANCE,
            next_step_label="PostgreSQL",
        )

        rendered = render_guided_step(snapshot)

        self.assertIn("Continuing to PostgreSQL in 5s", rendered)

    def test_terminal_screen_reuses_frame_in_place(self) -> None:
        stream = io.StringIO()
        screen = TerminalScreen(stream)

        screen.render("first\n")
        screen.render("second\n")
        screen.close()

        output = stream.getvalue()
        self.assertEqual(output.count(TerminalScreen.HIDE_CURSOR), 1)
        self.assertEqual(output.count(TerminalScreen.CURSOR_HOME), 2)
        self.assertEqual(output.count(TerminalScreen.ERASE_TO_END), 2)
        self.assertTrue(output.endswith(TerminalScreen.SHOW_CURSOR))


if __name__ == "__main__":
    unittest.main()
