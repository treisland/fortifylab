"""Contracts for sanitized wizard self-logging helpers."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/lib/wizard-logging.sh"


class WizardLoggingTests(unittest.TestCase):
    def run_helper(
        self, command: str, *, state: Path
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["XDG_STATE_HOME"] = str(state)
        environment["HOME"] = str(state.parent / "home")
        return subprocess.run(
            ["bash", "-c", 'source "$1"; shift; eval "$1"', "log-test", str(HELPER), command],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            env=environment,
        )

    def test_log_is_created_in_private_user_state_with_sanitized_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="customer-secret-token-") as directory:
            state = Path(directory) / "state"
            result = self.run_helper(
                "fortify_wizard_log INFO 'deploy password=abc123 token: xyz --client-secret supersecret https://user:pass@example.test/path'",
                state=state,
            )
            log_file = state / "fortify-lab/wizard.log"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(log_file.exists())
            content = log_file.read_text(encoding="utf-8")
            self.assertIn("[INFO] deploy", content)
            self.assertIn("password=[REDACTED]", content)
            self.assertIn("token: [REDACTED]", content)
            self.assertIn("--client-secret [REDACTED]", content)
            self.assertIn("https://user:[REDACTED]@example.test/path", content)
            self.assertNotIn("abc123", content)
            self.assertNotIn("xyz", content)
            self.assertNotIn("supersecret", content)
            self.assertNotIn(str(state), content)

            directory_mode = stat.S_IMODE((state / "fortify-lab").stat().st_mode)
            file_mode = stat.S_IMODE(log_file.stat().st_mode)
            self.assertEqual(directory_mode, 0o700)
            self.assertEqual(file_mode, 0o600)

    def test_relative_state_paths_are_rejected_without_repository_state(self) -> None:
        environment = os.environ.copy()
        environment["XDG_STATE_HOME"] = "relative-state"
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; fortify_wizard_log INFO hello',
                "log-test",
                str(HELPER),
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            env=environment,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((ROOT / "relative-state").exists())
        self.assertIn("absolute path", result.stderr)

    def test_size_based_rotation_uses_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            log_dir = state / "fortify-lab"
            log_dir.mkdir(parents=True)
            log_file = log_dir / "wizard.log"
            log_file.write_text("x" * 64, encoding="utf-8")
            result = self.run_helper(
                "FORTIFY_WIZARD_LOG_MAX_BYTES=32 FORTIFY_WIZARD_LOG_ROTATIONS=2 "
                "fortify_wizard_log WARN after-rotate",
                state=state,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((log_file.with_suffix(".log.1")).read_text(encoding="utf-8"), "x" * 64)
            self.assertIn("after-rotate", log_file.read_text(encoding="utf-8"))

            log_file.write_text("y" * 64, encoding="utf-8")
            second = self.run_helper(
                "FORTIFY_WIZARD_LOG_MAX_BYTES=32 FORTIFY_WIZARD_LOG_ROTATIONS=2 "
                "fortify_wizard_log WARN second-rotate",
                state=state,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((log_file.with_suffix(".log.1")).read_text(encoding="utf-8"), "y" * 64)
            self.assertEqual((log_file.with_suffix(".log.2")).read_text(encoding="utf-8"), "x" * 64)

    def test_tail_and_view_helpers_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            for index in range(5):
                result = self.run_helper(f"fortify_wizard_log INFO line-{index}", state=state)
                self.assertEqual(result.returncode, 0, result.stderr)

            tail = self.run_helper("fortify_wizard_log_tail 2", state=state)
            self.assertEqual(tail.returncode, 0, tail.stderr)
            self.assertNotIn("line-0", tail.stdout)
            self.assertIn("line-3", tail.stdout)
            self.assertIn("line-4", tail.stdout)

            invalid = self.run_helper("fortify_wizard_log_view invalid", state=state)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("non-negative integer", invalid.stderr)

    def test_invalid_rotation_configuration_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_helper(
                "FORTIFY_WIZARD_LOG_MAX_BYTES=invalid fortify_wizard_log INFO hello",
                state=Path(directory) / "state",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FORTIFY_WIZARD_LOG_MAX_BYTES", result.stderr)


if __name__ == "__main__":
    unittest.main()
