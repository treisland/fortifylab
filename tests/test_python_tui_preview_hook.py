"""M6: the opt-in FORTIFY_PYTHON_TUI_PREVIEW hook in start_wizard.sh.

This is deliberately an opt-in preview hook, not a default cutover: M2-M5
have not reached parity with the Bash 'more tools' menu (roughly half its
22 actions have no Python screen yet, and the ones that do are narrower
in scope -- see docs/development/python-tui-roadmap.md's M6 section).
These tests only cover the hook wiring itself, not menu parity.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIZARD = ROOT / "start_wizard.sh"


class PythonTuiPreviewHookTests(unittest.TestCase):
    def run_helper(self, command: str, *, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["WIZARD_NOMAIN"] = "1"
        environment.update(env_overrides or {})
        return subprocess.run(
            ["bash", "-c", 'source "$1"; shift; eval "$1"', "test", str(WIZARD), command],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            env=environment,
        )

    def test_not_requested_by_default(self) -> None:
        result = self.run_helper("fortifylab_python_tui_preview_requested")
        self.assertNotEqual(result.returncode, 0)

    def test_requested_when_env_var_is_1(self) -> None:
        result = self.run_helper(
            "fortifylab_python_tui_preview_requested",
            env_overrides={"FORTIFY_PYTHON_TUI_PREVIEW": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_other_values_do_not_count_as_requested(self) -> None:
        for value in ("0", "true", "yes", ""):
            result = self.run_helper(
                "fortifylab_python_tui_preview_requested",
                env_overrides={"FORTIFY_PYTHON_TUI_PREVIEW": value},
            )
            self.assertNotEqual(result.returncode, 0, f"value={value!r} should not count as requested")

    def test_launch_reaches_the_real_python_entrypoint(self) -> None:
        # No real TTY in a test process, so the Python side fails closed
        # (see fortifylab.tui.input.TerminalInput) -- that's the correct,
        # already-tested behavior; what this test confirms is that the
        # Bash hook actually execs into it rather than silently no-op'ing
        # or falling through to the Bash main_menu.
        result = self.run_helper("launch_python_tui_preview")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Python TUI preview", result.stdout)
        self.assertIn("requires a real terminal", result.stderr)

    def test_usage_documents_the_opt_in_variable(self) -> None:
        result = self.run_helper("usage")
        self.assertIn("FORTIFY_PYTHON_TUI_PREVIEW", result.stdout)

    def test_hook_is_wired_before_main_menu_not_replacing_it(self) -> None:
        # Confirms this is additive/opt-in: main_menu must still be the
        # unconditional fallback, unmodified, for every operator who
        # doesn't set the preview variable.
        source = WIZARD.read_text(encoding="utf-8")
        hook_index = source.index("fortifylab_python_tui_preview_requested")
        main_menu_call_index = source.rindex("\n    main_menu\n")
        self.assertLess(hook_index, main_menu_call_index)


if __name__ == "__main__":
    unittest.main()
