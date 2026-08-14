"""Contracts for the Phase 3.2 guided deployment TUI prototype."""

from __future__ import annotations

import io
import unittest

from fortifylab.status import EventSummary, LiveState, LiveStepStatus, PodSummary, ProgressHint, HintSeverity
from fortifylab.tui import ControlMode, GuidedStep, StepSnapshot, StepState, build_demo_snapshot, render_guided_step, step_snapshot_from_live
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

    def test_live_status_converts_to_guided_snapshot(self) -> None:
        live = LiveStepStatus(
            step_id="ssc",
            label="Software Security Center",
            state=LiveState.BLOCKED,
            detail="Waiting for image pull.",
            pods=(PodSummary("ssc-webapp-0", 0, 1, "Running", reason="ImagePullBackOff"),),
            events=(EventSummary("Warning", "ImagePullBackOff", "pod/ssc-webapp-0", "Back-off pulling image"),),
            hints=(ProgressHint("ssc", HintSeverity.BLOCKED, "image", "Image pull blocked.", "Check registry credentials."),),
        )

        snapshot = step_snapshot_from_live(live, index=9, total=13)
        rendered = render_guided_step(snapshot)

        self.assertEqual(snapshot.state, StepState.FAILED)
        self.assertIn("ssc-webapp-0", rendered)
        self.assertIn("Image pull blocked", rendered)


if __name__ == "__main__":
    unittest.main()
