"""Behavior and safety contracts for the lab/demo acknowledgement module."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/lib/lab-disclaimer.sh"
WIZARD = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
HELP = (ROOT / "scripts/lib/help.sh").read_text(encoding="utf-8")


class LabDisclaimerTests(unittest.TestCase):
    def run_helper(
        self, command: str, *, config: Path, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["XDG_CONFIG_HOME"] = str(config)
        environment["HOME"] = str(config.parent / "home")
        return subprocess.run(
            ["bash", "-c", 'source "$1"; shift; eval "$1"', "test", str(HELPER), command],
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            env=environment,
        )

    def test_exact_lab_response_records_success_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            result = self.run_helper(
                "fortify_lab_detect_accept_flag; fortify_lab_require_acknowledgement",
                config=config,
                input_text="LAB\n",
            )
            marker = config / "fortify-lab/acknowledged-lab-use"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "version=1\n")
            self.assertIn("does not limit the production capabilities", result.stdout)
            self.assertFalse((ROOT / "acknowledged-lab-use").exists())
            self.assertFalse((ROOT / ".env.lab-acknowledgement").exists())

    def test_refusal_and_eof_do_not_record_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            refused = self.run_helper(
                "fortify_lab_require_acknowledgement", config=config, input_text="yes\n"
            )
            eof = self.run_helper(
                "fortify_lab_require_acknowledgement", config=config, input_text=""
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertNotEqual(eof.returncode, 0)
            self.assertFalse((config / "fortify-lab/acknowledged-lab-use").exists())
            self.assertIn("declined", refused.stderr)
            self.assertIn("not received", eof.stderr)

    def test_explicit_noninteractive_flag_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "alternate-xdg"
            accepted = self.run_helper(
                "fortify_lab_detect_accept_flag --accept-lab-use; fortify_lab_require_acknowledgement",
                config=config,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn("explicit noninteractive option", accepted.stdout)
            reset = self.run_helper(
                "fortify_lab_reset_acknowledgement", config=config
            )
            self.assertEqual(reset.returncode, 0, reset.stderr)
            self.assertFalse((config / "fortify-lab/acknowledged-lab-use").exists())

    def test_output_is_sanitized_and_marker_contains_no_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="customer-secret-token-") as directory:
            config = Path(directory) / "private-config"
            result = self.run_helper(
                "fortify_lab_detect_accept_flag --accept-lab-use; fortify_lab_require_acknowledgement; "
                "fortify_lab_show_action_warning admin-token; "
                "fortify_lab_show_action_warning destructive; fortify_lab_menu_banner",
                config=config,
            )
            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(str(config), combined)
            self.assertNotIn("customer-secret-token", combined)
            marker = config / "fortify-lab/acknowledged-lab-use"
            self.assertEqual(marker.read_text(encoding="utf-8"), "version=1\n")
            self.assertIn("LAB / DEMO ONLY", combined)
            self.assertIn("administrator token grants full control", combined)
            self.assertIn("may not be recoverable", combined)


    def test_vulnerable_sample_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_helper(
                "fortify_lab_show_action_warning vulnerable-sample",
                config=Path(directory) / "config",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("intentionally vulnerable training targets", result.stdout)
            self.assertIn("isolated lab networks", result.stdout)

    def test_unrecognized_warning_context_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_helper(
                "fortify_lab_show_action_warning unknown",
                config=Path(directory) / "config",
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(str(Path(directory)), result.stderr)

    def test_welcome_banner_supports_version_no_color_and_disable_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            result = self.run_helper(
                "NO_COLOR=1 FORTIFYLAB_VERSION=vtest fortify_lab_welcome_banner",
                config=config,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FortifyLab vtest", result.stdout)
            self.assertIn("Ready-to-scan Fortify training lab", result.stdout)
            self.assertNotIn("\x1b[", result.stdout)

            disabled = self.run_helper(
                "FORTIFYLAB_VERSION=vtest FORTIFY_NO_BANNER=1 fortify_lab_welcome_banner",
                config=config,
            )
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertEqual(disabled.stdout, "")

    def test_welcome_banner_uses_quiet_narrow_terminal_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_helper(
                "COLUMNS=40 FORTIFYLAB_VERSION=vtest fortify_lab_welcome_banner",
                config=Path(directory) / "config",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FortifyLab vtest", result.stdout)
            self.assertNotIn("╭", result.stdout)

    def test_relative_xdg_path_cannot_create_repository_state(self) -> None:
        environment = os.environ.copy()
        environment["XDG_CONFIG_HOME"] = "relative-config"
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; fortify_lab_detect_accept_flag --accept-lab-use; '
                "fortify_lab_require_acknowledgement",
                "test",
                str(HELPER),
            ],
            text=True,
            capture_output=True,
            check=False,
            cwd=ROOT,
            env=environment,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((ROOT / "relative-config").exists())
        self.assertIn("absolute path", result.stderr)

    def test_wizard_wires_all_acknowledgement_boundaries(self) -> None:
        self.assertIn('source "$FORTIFY_HOME_K8S/scripts/lib/lab-disclaimer.sh"', WIZARD)
        self.assertIn('fortify_lab_detect_accept_flag "$@"', WIZARD)
        self.assertGreaterEqual(WIZARD.count("fortify_lab_require_acknowledgement"), 4)
        self.assertIn("fortify_lab_menu_banner", WIZARD)
        self.assertIn("fortify_lab_show_action_warning admin-token", WIZARD)
        self.assertIn("fortify_lab_show_action_warning destructive", WIZARD)
        self.assertIn("fortify_lab_reset_acknowledgement", HELP)
        self.assertIn("--accept-lab-use", WIZARD)


if __name__ == "__main__":
    unittest.main()
