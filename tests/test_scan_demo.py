"""Contracts for the first-scan one-click demo (SAST/IWA-Java)."""

from __future__ import annotations

import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class ScanDemoContractTests(unittest.TestCase):
    def test_wizard_wires_scan_demo_module_and_menu_entry(self) -> None:
        entrypoint = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        menu = (ROOT / "scripts" / "wizard" / "menu.sh").read_text(encoding="utf-8")
        self.assertIn("source_wizard_module scan-demo.sh", entrypoint)
        self.assertIn("scan_demo_menu", menu)
        self.assertIn("First-scan one-click demo", menu)

    def test_scan_demo_module_defines_the_full_scan_type_shape(self) -> None:
        module = (ROOT / "scripts" / "wizard" / "scan-demo.sh").read_text(encoding="utf-8")
        for fn in (
            "scan_type_prereqs_sast_iwa_java",
            "scan_type_login_sast_iwa_java",
            "scan_type_sensor_check_sast_iwa_java",
            "scan_type_acquire_sast_iwa_java",
            "scan_type_package_sast_iwa_java",
            "scan_type_submit_sast_iwa_java",
            "scan_type_poll_sast_iwa_java",
            "scan_type_verify_sast_iwa_java",
            "scan_type_results_sast_iwa_java",
            "scan_type_logout_sast_iwa_java",
        ):
            self.assertIn(f"{fn}()", module)

    def test_repo_url_defaults_to_the_official_iwa_java_repository(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            unset FORTIFY_FIRST_SCAN_REPO_URL
            source "$1"
            printf 'REPO_URL=%s\\n' "$FORTIFY_FIRST_SCAN_REPO_URL"
        """
        result = subprocess.run(
            ["bash", "-c", command, "repo-url-default-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertIn("REPO_URL=https://github.com/fortify/IWA-Java", result.stdout)

    def test_prereqs_refuse_to_run_if_repo_url_is_explicitly_cleared(self) -> None:
        # A user can still override the default to empty; this must fail
        # loudly rather than silently cloning nothing.
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            SSC_URL=https://ssc.fortifylab.test
            FORTIFY_FIRST_SCAN_REPO_URL=
            scan_type_prereqs_sast_iwa_java
            printf 'RC=%s\\n' "$?"
        """
        result = subprocess.run(
            ["bash", "-c", command, "prereqs-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertIn("RC=1", result.stdout)
        self.assertIn("FORTIFY_FIRST_SCAN_REPO_URL is empty", result.stdout + result.stderr)

    def test_prereqs_pass_when_fcli_and_ssc_url_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            _write_executable(bin_dir / "fcli", "#!/usr/bin/env bash\nexit 0\n")
            command = """
                export WIZARD_NOMAIN=1 NO_COLOR=1
                export FORTIFY_FCLI_INSTALL_DIR="$2"
                export PATH="$2:$PATH"
                source "$1"
                SSC_URL=https://ssc.fortifylab.test
                FORTIFY_FIRST_SCAN_REPO_URL=https://example.invalid/iwa-java.git
                scan_type_prereqs_sast_iwa_java
                printf 'RC=%s\\n' "$?"
            """
            result = subprocess.run(
                ["bash", "-c", command, "prereqs-ok-test", str(ROOT / "start_wizard.sh"), str(bin_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertIn("RC=0", result.stdout, result.stdout + result.stderr)

    def test_sensor_check_fails_closed_when_no_sensor_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "fcli",
                "#!/usr/bin/env bash\n"
                'if [[ "$*" == *"sensor list"* ]]; then printf \'No sensors found\\n\'; exit 0; fi\n'
                "exit 0\n",
            )
            command = """
                export WIZARD_NOMAIN=1 NO_COLOR=1
                export FORTIFY_FCLI_INSTALL_DIR="$2"
                export PATH="$2:$PATH"
                source "$1"
                scan_type_sensor_check_sast_iwa_java
                printf 'RC=%s\\n' "$?"
            """
            result = subprocess.run(
                ["bash", "-c", command, "sensor-test", str(ROOT / "start_wizard.sh"), str(bin_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertIn("RC=1", result.stdout)
            self.assertIn("No ScanCentral SAST sensor is registered", result.stdout + result.stderr)

    def test_sensor_check_passes_when_a_sensor_is_listed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            _write_executable(
                bin_dir / "fcli",
                "#!/usr/bin/env bash\n"
                'if [[ "$*" == *"sensor list"* ]]; then printf \'sensor-01  IDLE  4.5\\n\'; exit 0; fi\n'
                "exit 0\n",
            )
            command = """
                export WIZARD_NOMAIN=1 NO_COLOR=1
                export FORTIFY_FCLI_INSTALL_DIR="$2"
                export PATH="$2:$PATH"
                source "$1"
                scan_type_sensor_check_sast_iwa_java
                printf 'RC=%s\\n' "$?"
            """
            result = subprocess.run(
                ["bash", "-c", command, "sensor-ok-test", str(ROOT / "start_wizard.sh"), str(bin_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertIn("RC=0", result.stdout, result.stdout + result.stderr)

    def test_verify_treats_faulted_state_as_failure_not_success(self) -> None:
        # This is the "wait-for doesn't guarantee success" gap identified
        # during design review: a terminal state must not be reported as a
        # successful scan just because polling stopped.
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            LAST_SCAN_STATUS="scanState: FAULTED, publishState: NO_PUBLISH"
            scan_type_verify_sast_iwa_java
            printf 'RC=%s\\n' "$?"
        """
        result = subprocess.run(
            ["bash", "-c", command, "verify-faulted-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertIn("RC=1", result.stdout)
        self.assertIn("did not complete successfully", result.stdout + result.stderr)

    def test_verify_accepts_completed_state_as_success(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            LAST_SCAN_STATUS="scanState: COMPLETED, publishState: COMPLETED"
            scan_type_verify_sast_iwa_java
            printf 'RC=%s\\n' "$?"
        """
        result = subprocess.run(
            ["bash", "-c", command, "verify-completed-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertIn("RC=0", result.stdout, result.stdout + result.stderr)

    def test_login_does_not_leak_the_token_shape_when_sc_sast_url_unset(self) -> None:
        # Regression guard for the array-expansion bug shape: an unset
        # SCSAST_CTRL_URL must not inject a literal '--sc-sast-url ""' or
        # stray quote characters into the fcli invocation.
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            call_log = Path(directory) / "calls.log"
            _write_executable(
                bin_dir / "fcli",
                "#!/usr/bin/env bash\n"
                f'printf \'%s\\n\' "$*" >> "{call_log}"\n'
                "exit 0\n",
            )
            command = """
                export WIZARD_NOMAIN=1 NO_COLOR=1
                export FORTIFY_FCLI_INSTALL_DIR="$2"
                export PATH="$2:$PATH"
                source "$1"
                SSC_URL=https://ssc.fortifylab.test
                FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
                unset SCSAST_CTRL_URL
                scan_type_login_sast_iwa_java "synthetic-token"
                printf 'RC=%s\\n' "$?"
            """
            result = subprocess.run(
                ["bash", "-c", command, "login-test", str(ROOT / "start_wizard.sh"), str(bin_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertIn("RC=0", result.stdout, result.stdout + result.stderr)
            calls = call_log.read_text(encoding="utf-8")
            self.assertNotIn('""', calls)
            self.assertNotIn("--sc-sast-url", calls)
            self.assertIn("--token=synthetic-token", calls)
            self.assertNotIn("--ci-token", calls)

    def test_login_includes_client_auth_token_when_readable_from_kubernetes(self) -> None:
        # Regression guard: fcli's SC-SAST session (used later for sensor
        # list/package/submit) is not actually authenticated without
        # --client-auth-token, even though the SSC login itself succeeds
        # without it -- confirmed against a real fcli's working invocation.
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            call_log = Path(directory) / "calls.log"
            _write_executable(
                bin_dir / "fcli",
                "#!/usr/bin/env bash\n"
                f'printf \'%s\\n\' "$*" >> "{call_log}"\n'
                "exit 0\n",
            )
            command = """
                export WIZARD_NOMAIN=1 NO_COLOR=1
                export FORTIFY_FCLI_INSTALL_DIR="$2"
                export PATH="$2:$PATH"
                source "$1"
                SSC_URL=https://ssc.fortifylab.test
                FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
                credential_value_from_secret() { printf 'synthetic-client-auth-token\\n'; }
                scan_type_login_sast_iwa_java "synthetic-token"
                printf 'RC=%s\\n' "$?"
            """
            result = subprocess.run(
                ["bash", "-c", command, "login-cat-test", str(ROOT / "start_wizard.sh"), str(bin_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertIn("RC=0", result.stdout, result.stdout + result.stderr)
            calls = call_log.read_text(encoding="utf-8")
            self.assertIn("--client-auth-token synthetic-client-auth-token", calls)

    def test_login_warns_but_continues_when_client_auth_token_is_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            call_log = Path(directory) / "calls.log"
            _write_executable(
                bin_dir / "fcli",
                "#!/usr/bin/env bash\n"
                f'printf \'%s\\n\' "$*" >> "{call_log}"\n'
                "exit 0\n",
            )
            command = """
                export WIZARD_NOMAIN=1 NO_COLOR=1
                export FORTIFY_FCLI_INSTALL_DIR="$2"
                export PATH="$2:$PATH"
                source "$1"
                SSC_URL=https://ssc.fortifylab.test
                FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
                credential_value_from_secret() { return 1; }
                scan_type_login_sast_iwa_java "synthetic-token"
                printf 'RC=%s\\n' "$?"
            """
            result = subprocess.run(
                ["bash", "-c", command, "login-cat-missing-test", str(ROOT / "start_wizard.sh"), str(bin_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertIn("RC=0", result.stdout, result.stdout + result.stderr)
            self.assertIn("Could not read the ScanCentral SAST client auth token", result.stdout + result.stderr)
            calls = call_log.read_text(encoding="utf-8")
            self.assertNotIn("--client-auth-token", calls)

    def test_acquire_session_reuses_an_already_usable_session_without_logging_in(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
            scan_type_session_usable_sast_iwa_java() { return 0; }
            scan_type_login_sast_iwa_java() { echo LOGIN_CALLED_UNEXPECTEDLY; return 1; }
            scan_demo_acquire_session; rc=$?
            printf 'RC=%s OWNED=%s\\n' "$rc" "$SCAN_DEMO_SESSION_OWNED"
        """
        result = subprocess.run(
            ["bash", "-c", command, "acquire-reuse-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RC=0 OWNED=0", result.stdout)
        self.assertNotIn("LOGIN_CALLED_UNEXPECTEDLY", result.stdout)
        self.assertIn("Reusing the existing SSC session", result.stdout)

    def test_acquire_session_uses_fcli_default_ssc_token_without_prompting(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
            FCLI_DEFAULT_SSC_TOKEN=env-supplied-token
            scan_type_session_usable_sast_iwa_java() { return 1; }
            scan_type_login_sast_iwa_java() { printf 'LOGIN_TOKEN=%s\\n' "$1"; }
            scan_demo_acquire_session; rc=$?
            printf 'RC=%s OWNED=%s\\n' "$rc" "$SCAN_DEMO_SESSION_OWNED"
        """
        # No stdin provided: this path must not block on a prompt.
        result = subprocess.run(
            ["bash", "-c", command, "acquire-env-token-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            input="",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOGIN_TOKEN=env-supplied-token", result.stdout)
        self.assertIn("RC=0 OWNED=1", result.stdout)
        self.assertIn("FCLI_DEFAULT_SSC_TOKEN", result.stdout)

    def test_acquire_session_falls_back_to_interactive_prompt(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
            unset FCLI_DEFAULT_SSC_TOKEN
            scan_type_session_usable_sast_iwa_java() { return 1; }
            scan_type_login_sast_iwa_java() { printf 'LOGIN_TOKEN=%s\\n' "$1"; }
            scan_demo_acquire_session; rc=$?
            printf 'RC=%s OWNED=%s\\n' "$rc" "$SCAN_DEMO_SESSION_OWNED"
        """
        result = subprocess.run(
            ["bash", "-c", command, "acquire-prompt-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            input="pasted-token\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOGIN_TOKEN=pasted-token", result.stdout)
        self.assertIn("RC=0 OWNED=1", result.stdout)

    def test_acquire_session_reports_cancel_distinctly_from_failure(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
            unset FCLI_DEFAULT_SSC_TOKEN
            scan_type_session_usable_sast_iwa_java() { return 1; }
            scan_type_login_sast_iwa_java() { echo LOGIN_CALLED_UNEXPECTEDLY; }
            scan_demo_acquire_session
            printf 'RC=%s\\n' "$?"
        """
        result = subprocess.run(
            ["bash", "-c", command, "acquire-cancel-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            input="\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RC=2", result.stdout)
        self.assertNotIn("LOGIN_CALLED_UNEXPECTEDLY", result.stdout)

    def test_menu_only_logs_out_a_session_it_created_itself(self) -> None:
        stub_functions = """
            title() { :; }
            press_any() { :; }
            confirm() { return 0; }
            scan_type_prereqs_sast_iwa_java() { return 0; }
            scan_type_login_sast_iwa_java() { return 0; }
            scan_type_sensor_check_sast_iwa_java() { return 0; }
            scan_type_acquire_sast_iwa_java() { return 0; }
            scan_type_package_sast_iwa_java() { return 0; }
            scan_type_submit_sast_iwa_java() { return 0; }
            scan_type_poll_sast_iwa_java() { return 0; }
            scan_type_verify_sast_iwa_java() { return 0; }
            scan_type_results_sast_iwa_java() { :; }
            scan_type_logout_sast_iwa_java() { echo LOGOUT_CALLED; }
        """
        for session_usable, expect_logout, stdin in (
            (1, False, ""),
            (0, True, "pasted-token\n"),
        ):
            with self.subTest(session_usable=session_usable):
                command = f"""
                    export WIZARD_NOMAIN=1 NO_COLOR=1
                    source "$1"
                    FORTIFY_FIRST_SCAN_SSC_SESSION=fortifylab-first-scan
                    FORTIFY_FIRST_SCAN_APP=IWA-Java
                    {stub_functions}
                    scan_type_session_usable_sast_iwa_java() {{ return {1 - session_usable}; }}
                    scan_demo_menu
                """
                result = subprocess.run(
                    ["bash", "-c", command, f"menu-logout-{session_usable}-test", str(ROOT / "start_wizard.sh")],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    input=stdin,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if expect_logout:
                    self.assertIn("LOGOUT_CALLED", result.stdout)
                else:
                    self.assertNotIn("LOGOUT_CALLED", result.stdout)


if __name__ == "__main__":
    unittest.main()
