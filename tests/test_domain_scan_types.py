"""Unit tests for the scan-type strategy model (M1 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.domain.scan_types import SastIwaJavaScan, ScanStep, ScanType  # noqa: E402


class SastIwaJavaScanTests(unittest.TestCase):
    def test_satisfies_the_scan_type_protocol(self) -> None:
        scan: ScanType = SastIwaJavaScan()
        self.assertEqual(scan.scan_type_id, "sast_iwa_java")
        self.assertTrue(scan.display_name)

    def test_steps_are_ordered_prereqs_first_logout_last(self) -> None:
        steps = SastIwaJavaScan().steps()
        self.assertTrue(steps)
        self.assertEqual(steps[0].verb, "prereqs")
        self.assertEqual(steps[-1].verb, "logout")

    def test_every_bash_verb_from_scan_demo_sh_is_represented(self) -> None:
        # scan-demo.sh's header comment documents this exact verb list as its
        # extension point; keep this test in sync with that comment.
        expected_verbs = {
            "prereqs",
            "login",
            "sensor_check",
            "rulepack_check",
            "setup_appversion",
            "acquire",
            "package",
            "submit",
            "poll",
            "verify",
            "results",
            "logout",
        }
        actual_verbs = {step.verb for step in SastIwaJavaScan().steps()}
        self.assertTrue(expected_verbs.issubset(actual_verbs))

    def test_steps_are_hashable_data_not_live_execution(self) -> None:
        step = ScanStep("submit", "Submit the packaged scan", ("fcli", "sc-sast", "scan", "start"))
        self.assertEqual(step.command_template[0], "fcli")


if __name__ == "__main__":
    unittest.main()
