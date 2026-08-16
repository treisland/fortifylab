"""Contracts for the Python CLI/TUI operator console."""

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
from fortifylab.tui import OPERATOR_MENU, OperatorConsole, TerminalStyle, render_operator_menu  # noqa: E402


class PythonOperatorConsoleTests(unittest.TestCase):
    def run_module(self, *args: str, no_color: bool = False, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        if no_color:
            env["NO_COLOR"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "fortifylab", *args],
            cwd=ROOT,
            env=env,
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )

    def scripted_console(self, responses: list[str], *, dashboard: str = "DASHBOARD SCREEN\n") -> tuple[int, str, list[tuple[str, ...]]]:
        output: list[str] = []
        commands: list[tuple[str, ...]] = []
        iterator = iter(responses)

        def input_fn(_prompt: str) -> str:
            return next(iterator)

        def output_fn(text: str) -> None:
            output.append(text)

        def command_runner(command: tuple[str, ...]) -> int:
            commands.append(command)
            return 0

        console = OperatorConsole(
            style=TerminalStyle(color=False, symbols=False),
            input_fn=input_fn,
            output_fn=output_fn,
            command_runner=command_runner,
            dashboard_factory=lambda: dashboard,
        )
        return console.run(), "\n".join(output), commands

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

    def test_operator_menu_has_task_oriented_workspaces_and_preview_mode(self) -> None:
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

        operational = render_operator_menu(style=TerminalStyle(color=False, symbols=False), preview=False)
        self.assertIn("Select a workspace", operational)
        self.assertNotIn("Preview only", operational)

        result = self.run_module("menu", "--plain", "--preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Task workspaces", result.stdout)
        self.assertIn("Preview only", result.stdout)
        self.assertNotIn("\033[", result.stdout)

    def test_menu_command_enters_interactive_loop_and_can_quit(self) -> None:
        result = self.run_module("menu", "--plain", stdin="q\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fortify Lab Operator Console", result.stdout)
        self.assertIn("Goodbye", result.stdout)

    def test_interactive_dashboard_route_uses_injected_dashboard(self) -> None:
        rc, output, commands = self.scripted_console(["1", "", "q"])
        self.assertEqual(rc, 0)
        self.assertIn("DASHBOARD SCREEN", output)
        self.assertEqual(commands, [])

    def test_invalid_input_recovers_before_quit(self) -> None:
        rc, output, commands = self.scripted_console(["nope", "99", "q"])
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(output.count("Invalid selection. Choose a number shown above or q to quit."), 2)
        self.assertEqual(commands, [])

    def test_configuration_route_runs_read_only_command_with_runner_hook(self) -> None:
        rc, output, commands = self.scripted_console(["4", "1", "", "b", "q"])
        self.assertEqual(rc, 0)
        self.assertIn("Configuration", output)
        self.assertIn("Action completed", output)
        self.assertEqual(commands, [("./bin/fortifylab", "config", "diagnostics")])

    def test_deploy_handoff_requires_confirmation_before_running_script(self) -> None:
        rc, output, commands = self.scripted_console(["2", "1", "n", "", "b", "q"])
        self.assertEqual(rc, 0)
        self.assertIn("Start or resume guided deployment", output)
        self.assertIn("Skipped", output)
        self.assertEqual(commands, [])

    def test_deploy_handoff_runs_script_after_confirmation(self) -> None:
        rc, output, commands = self.scripted_console(["2", "1", "yes", "", "b", "q"])
        self.assertEqual(rc, 0)
        self.assertIn("Action completed", output)
        self.assertEqual(commands, [("./start_wizard.sh",)])

    def test_tools_and_help_routes_render_operator_guidance(self) -> None:
        rc, output, commands = self.scripted_console(["9", "", "10", "", "q"])
        self.assertEqual(rc, 0)
        self.assertIn("Optional dependencies", output)
        self.assertIn("Mutating deployment actions ask for confirmation", output)
        self.assertEqual(commands, [])

    def test_dashboard_demo_command_renders_read_only_preview(self) -> None:
        result = self.run_module("dashboard", "--demo", "--plain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fortify Lab Dashboard", result.stdout)
        self.assertIn("Source:   demo", result.stdout)
        self.assertIn("Software Security Center", result.stdout)


if __name__ == "__main__":
    unittest.main()
