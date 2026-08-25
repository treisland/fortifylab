"""M1 acceptance tests for the Python TUI skeleton entrypoints.

These tests intentionally cover only clone-and-run surfaces. They must not
require Kubernetes, Helm, Docker, network access, or interactive terminal input.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class M1EntrypointTests(unittest.TestCase):
    maxDiff = None

    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["NO_COLOR"] = "1"
        env["FORTIFYLAB_TUI_TEST_MODE"] = "1"
        return subprocess.run(
            [*args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def test_bin_help_is_clone_safe(self) -> None:
        result = self.run_command(str(ROOT / "bin" / "fortifylab"), "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fortifylab", result.stdout.lower())
        self.assertIn("tui", result.stdout.lower())
        self.assertNotIn("kubectl", result.stderr.lower())
        self.assertNotIn("helm", result.stderr.lower())

    def test_tui_smoke_test_exits_without_interactive_terminal(self) -> None:
        result = self.run_command(str(ROOT / "bin" / "fortifylab"), "tui", "--smoke-test")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FortifyLab", result.stdout)
        self.assertIn("TUI", result.stdout)
        self.assertRegex(result.stdout, r"M1.*(placeholder|skeleton)")

    def test_python_package_imports_from_repo_root(self) -> None:
        result = self.run_command(
            sys.executable,
            "-c",
            "import fortifylab; print(getattr(fortifylab, '__version__', 'missing'))",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), "missing")

    def test_start_wizard_is_removed_or_deliberate_shim(self) -> None:
        shim = ROOT / "start_wizard.sh"
        if not shim.exists():
            return

        self.assertTrue(os.access(shim, os.X_OK))
        text = shim.read_text(encoding="utf-8")
        forbidden_legacy_markers = (
            "source_wizard_module",
            "main_menu",
            "scripts/wizard/menu.sh",
            "scripts/wizard/operations.sh",
        )
        for marker in forbidden_legacy_markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)
        self.assertRegex(text, r"(bin/fortifylab|python3 -m fortifylab)")

        result = self.run_command(str(shim), "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fortifylab", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
