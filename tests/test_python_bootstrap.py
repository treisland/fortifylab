"""Contracts for Phase 3.8 bootstrap and migration checks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fortifylab.bootstrap import check_clone_layout, check_compatibility_wrappers, check_python_version, check_runtime_directories, run_bootstrap_checks
from fortifylab.runtime import compatibility_report, runtime_paths, write_runtime_log


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

    def test_runtime_paths_default_to_repo_log_directory(self) -> None:
        paths = runtime_paths(ROOT)

        self.assertEqual(paths.log_dir, ROOT / ".fortifylab" / "logs")
        self.assertEqual(paths.log_file.name, "fortifylab.log")

    def test_runtime_directory_check_reports_log_path(self) -> None:
        check = check_runtime_directories(ROOT)

        self.assertTrue(check.ok, check)
        self.assertIn(".fortifylab", check.detail)

    def test_runtime_log_redacts_secret_like_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = write_runtime_log("token=supersecret", repo_root=ROOT, log_dir=tmp)
            text = log_file.read_text(encoding="utf-8")

        self.assertIn("token=<redacted>", text)
        self.assertNotIn("supersecret", text)

    def test_compatibility_report_is_read_only_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bin").mkdir()
            (root / "scripts" / "wizard").mkdir(parents=True)
            (root / "src" / "fortifylab").mkdir(parents=True)
            (root / "start_wizard.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / "bin" / "fortifylab").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / ".env").write_text("DOMAIN=fortifydemo.com\nSSC=ssc.$DOMAIN\nSSC_URL=https://$SSC\n", encoding="utf-8")

            report = compatibility_report(root)

        names = {item.name for item in report}
        self.assertIn(".env", names)
        self.assertIn("certificates", names)
        self.assertIn("secrets", names)


if __name__ == "__main__":
    unittest.main()
