"""Contracts for the Fortify Lab Python CLI preview."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class PythonCliTests(unittest.TestCase):
    def run_module(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return subprocess.run(
            [sys.executable, "-m", "fortifylab", *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_module_help_discovers_initial_commands(self) -> None:
        result = self.run_module("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("doctor", "config", "deploy", "logs", "runbook", "tui"):
            with self.subTest(command=command):
                self.assertIn(command, result.stdout)

    def test_wrapper_version_works_from_clone(self) -> None:
        result = subprocess.run(
            [str(ROOT / "bin" / "fortifylab"), "--version"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fortifylab 3.1.0-preview", result.stdout)

    def test_placeholder_commands_are_clear(self) -> None:
        for command in ("doctor", "config", "deploy", "logs", "runbook", "tui"):
            with self.subTest(command=command):
                result = self.run_module(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Python", result.stdout)
                self.assertIn("available", result.stdout)

    def test_tui_demo_screen_renders_guided_step(self) -> None:
        result = self.run_module("tui", "--demo-screen")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Guided deployment - Step 9 of 13", result.stdout)
        self.assertIn("Verifying Software Security Center", result.stdout)
        self.assertIn("p. Pod logs", result.stdout)

    def test_deploy_plan_prints_dry_run_orchestration_plan(self) -> None:
        result = self.run_module("deploy", "--plan", "ssc_only")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Deployment plan: SSC only", result.stdout)
        self.assertIn("./apps/ssc/start.sh", result.stdout)
        self.assertIn("depends on: mysql", result.stdout)


if __name__ == "__main__":
    unittest.main()
