"""Tests for fortifylab.app.run_tui, the interactive TUI composition root."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.app import run_tui  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402


class RunTuiWithInjectedEventsTests(unittest.TestCase):
    def test_navigates_and_quits_without_touching_a_real_terminal(self) -> None:
        output = io.StringIO()
        exit_code = run_tui(
            events=[KeyEvent("down"), KeyEvent("enter"), KeyEvent("q")],
            output_stream=output,
        )
        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        self.assertIn("Fortify Lab Operator Console", rendered)
        self.assertIn("Preview:", rendered)


class RunTuiInteractiveCliTests(unittest.TestCase):
    def test_interactive_flag_fails_closed_without_a_tty(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        result = subprocess.run(
            [sys.executable, "-m", "fortifylab", "tui", "--interactive"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires a real terminal", result.stderr)


if __name__ == "__main__":
    unittest.main()
