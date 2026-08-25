"""Contracts for safe Python subprocess adapters."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import redact_text, run_command  # noqa: E402


class PythonCommandAdapterTests(unittest.TestCase):
    def test_success_result_is_structured(self) -> None:
        result = run_command([sys.executable, "-c", "print('ok')"])
        self.assertTrue(result.ok)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ok")
        self.assertFalse(result.timed_out)
        self.assertGreaterEqual(result.duration_seconds, 0)

    def test_failure_does_not_raise(self) -> None:
        result = run_command([sys.executable, "-c", "import sys; print('bad'); sys.exit(7)"])
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 7)
        self.assertIn("bad", result.stdout)

    def test_timeout_returns_124_and_marks_timed_out(self) -> None:
        result = run_command([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.1)
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)
        self.assertIn("timed out", result.stderr)

    def test_redacts_secret_like_output(self) -> None:
        text = "password=hunter2 token=abc secret=sauce api_key=key123\nAuthorization: Bearer abc123"
        redacted = redact_text(text)
        for sensitive in ("hunter2", "abc", "sauce", "key123", "Bearer abc123"):
            self.assertNotIn(sensitive, redacted)
        self.assertIn("password=<redacted>", redacted)
        self.assertIn("Authorization=<redacted>", redacted)

    def test_command_result_redacts_stdout_and_stderr(self) -> None:
        code = "import sys; print('token=abc123'); print('password=oops', file=sys.stderr)"
        result = run_command([sys.executable, "-c", code])
        self.assertNotIn("abc123", result.stdout)
        self.assertNotIn("oops", result.stderr)
        self.assertIn("token=<redacted>", result.stdout)
        self.assertIn("password=<redacted>", result.stderr)


if __name__ == "__main__":
    unittest.main()
