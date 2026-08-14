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
        for command in ("doctor", "config", "deploy", "logs", "runbook", "tui", "web"):
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
        for command in ("doctor", "config", "deploy", "logs", "runbook", "tui", "web"):
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

    def test_config_validate_reports_invalid_placeholder_values(self) -> None:
        env_file = ROOT / ".tmp-python-config-test.env"
        env_file.write_text("DOMAIN=fortifydemo.com\nSSC=LIM\nSSC_URL=LIM_URL\n", encoding="utf-8")
        try:
            result = self.run_module("config", "validate", "--env", str(env_file))
        finally:
            env_file.unlink(missing_ok=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("SSC is set to placeholder-like value LIM", result.stdout)
        self.assertIn("SSC_URL is set to placeholder-like value LIM_URL", result.stdout)

    def test_config_repair_dry_run_and_json_diagnostics_work(self) -> None:
        env_file = ROOT / ".tmp-python-config-test.env"
        env_file.write_text("DOMAIN=FortifyDemo.PROXMOX\nSSC=LIM\nSSC_URL=LIM_URL\n", encoding="utf-8")
        try:
            repair = self.run_module("config", "repair-derived", "--env", str(env_file), "--domain", "FortifyDemo.PROXMOX")
            diagnostics = self.run_module("config", "diagnostics", "--env", str(env_file), "--json")
            after = env_file.read_text(encoding="utf-8")
        finally:
            env_file.unlink(missing_ok=True)

        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertIn("DOMAIN", repair.stdout)
        self.assertIn("Dry run; no changes written", repair.stdout)
        self.assertIn("FortifyDemo.PROXMOX", after)
        self.assertEqual(diagnostics.returncode, 0, diagnostics.stderr)
        self.assertIn('"issues"', diagnostics.stdout)

    def test_doctor_bundle_writes_sanitized_archive(self) -> None:
        bundle_dir = ROOT / ".tmp-python-diagnostics"
        try:
            result = self.run_module("doctor", "--bundle-dir", str(bundle_dir))
        finally:
            bundle = bundle_dir / "fortifylab-diagnostics.tar.gz"
            if bundle.exists():
                bundle.unlink()
            bundle_dir.rmdir()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Diagnostics bundle:", result.stdout)

    def test_deploy_operation_dry_runs_mutating_operations(self) -> None:
        result = self.run_module("deploy", "--operation", "secrets")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Operation: secrets.create", result.stdout)
        self.assertIn("Executed: false", result.stdout)
        self.assertIn("Dry run", result.stdout)

    def test_web_check_blocks_lan_without_token(self) -> None:
        result = self.run_module("web", "--check", "--bind", "0.0.0.0", "--allow-lan")

        self.assertEqual(result.returncode, 1)
        self.assertIn("LAN access requires an access token", result.stdout)

    def test_web_check_reports_local_api_summary(self) -> None:
        result = self.run_module("web", "--check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("web console check: 200", result.stdout)
        self.assertIn("operations:", result.stdout)

    def test_doctor_environment_reports_bootstrap_checks(self) -> None:
        result = self.run_module("doctor", "--environment")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("python-version: ok", result.stdout)
        self.assertIn("clone-layout: ok", result.stdout)
        self.assertIn("compatibility-wrappers: ok", result.stdout)
        self.assertIn("runtime-directories: ok", result.stdout)
        self.assertIn("runtime-log: ok", result.stdout)

    def test_doctor_compatibility_reports_migration_inputs(self) -> None:
        result = self.run_module("doctor", "--compatibility")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".env:", result.stdout)
        self.assertIn("certificates:", result.stdout)
        self.assertIn("runtime-log:", result.stdout)


if __name__ == "__main__":
    unittest.main()
