"""Contracts for the Python CLI/TUI operator console preview."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.dependencies import dependency_checks, migration_status_lines  # noqa: E402
from fortifylab.tui import OPERATOR_MENU, TerminalStyle, render_operator_menu  # noqa: E402


class PythonOperatorConsoleTests(unittest.TestCase):
    def run_module(self, *args: str, no_color: bool = False) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        if no_color:
            env["NO_COLOR"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "fortifylab", *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_migration_status_declares_cli_tui_and_bash_boundary(self) -> None:
        lines = "\n".join(migration_status_lines())
        self.assertIn("CLI/TUI", lines)
        self.assertIn("./start_wizard.sh", lines)
        self.assertIn("Bash compatibility", lines)
        self.assertIn("Web UI: out of active migration scope", lines)

        result = self.run_module("status", "--dependencies")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Python runtime", result.stdout)
        self.assertIn("Optional dependencies", result.stdout)
        for name in ("rich", "textual", "pydantic", "typer"):
            self.assertIn(name, result.stdout)

    def test_dependency_checks_are_optional_and_non_importing(self) -> None:
        checks = dependency_checks()
        self.assertEqual({check.name for check in checks}, {"rich", "textual", "pydantic", "typer"})
        self.assertTrue(all(not check.required for check in checks))
        self.assertTrue(all(check.state in {"available", "optional"} for check in checks))

    def test_operator_menu_has_task_oriented_workspaces_and_plain_mode(self) -> None:
        labels = [item.label for item in OPERATOR_MENU]
        for label in (
            "Dashboard",
            "Deploy / Resume",
            "Applications",
            "Configuration",
            "Runbooks",
            "Logs",
            "Diagnostics",
            "Certificates & Trust",
            "Tools",
            "Help",
        ):
            self.assertIn(label, labels)

        rendered = render_operator_menu(style=TerminalStyle(color=False, symbols=False))
        self.assertIn("Fortify Lab Operator Console", rendered)
        self.assertIn("Preview only", rendered)
        self.assertNotIn("\033[", rendered)

        result = self.run_module("menu", "--plain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Task workspaces", result.stdout)
        self.assertNotIn("\033[", result.stdout)

    def test_dashboard_demo_command_renders_read_only_preview(self) -> None:
        result = self.run_module("dashboard", "--demo", "--plain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fortify Lab Dashboard", result.stdout)
        self.assertIn("Source:   demo", result.stdout)
        self.assertIn("Software Security Center", result.stdout)


if __name__ == "__main__":
    unittest.main()
