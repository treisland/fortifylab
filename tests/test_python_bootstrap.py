"""Contracts for Phase 3.8 bootstrap and migration checks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fortifylab.bootstrap import check_clone_layout, check_compatibility_wrappers, check_python_version, run_bootstrap_checks


class PythonBootstrapTests(unittest.TestCase):
    def test_python_version_check_requires_supported_runtime(self) -> None:
        self.assertFalse(check_python_version((3, 9)).ok)
        self.assertTrue(check_python_version((3, 10)).ok)

    def test_clone_layout_reports_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            check = check_clone_layout(Path(tmp))

        self.assertFalse(check.ok)
        self.assertIn("bin/fortifylab", check.detail)

    def test_current_repo_has_bootstrap_paths_and_wrappers(self) -> None:
        checks = run_bootstrap_checks(ROOT)


        self.assertTrue(all(check.ok for check in checks), checks)
        self.assertTrue(check_compatibility_wrappers(ROOT).ok)


if __name__ == "__main__":
    unittest.main()
