"""Static safety contracts for the wizard-only deployment repository."""

from __future__ import annotations

import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WizardContractTests(unittest.TestCase):
    def test_fresh_install_versions_match_current_chart_contracts(self) -> None:
        environment = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn('FORTIFY_SSC_CHART_VERSION="26.2.0-1"', environment)
        self.assertIn('FORTIFY_SCSAST_CHART_VERSION="26.2.0-1"', environment)

    def test_dependency_waits_abort_the_deployment(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        for gate in ("mysql", "postgresql", "ssc", "lim"):
            self.assertIn(f"health_{gate}_ready || return", wizard)
        self.assertNotIn('"pod/$pod" || true', wizard)

    def test_fresh_install_refuses_existing_managed_releases(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        self.assertIn("Managed releases already exist", wizard)
        self.assertIn("Apps → Start / Upgrade", wizard)

    def test_removed_products_do_not_return(self) -> None:
        self.assertFalse((ROOT / "manager").exists())
        self.assertFalse((ROOT / "supervisor").exists())
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True
        ).splitlines()
        self.assertFalse(any(path.startswith("apps/jenkins/") for path in tracked))
        self.assertFalse(any(path.startswith("apps/sonatype/") for path in tracked))

    def test_credentials_are_not_printed_or_passed_to_helm(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        sast = (ROOT / "apps/scsast/start.sh").read_text(encoding="utf-8")
        app_credentials = wizard.split("show_app_creds()", 1)[1].split(
            "# License menu", 1
        )[0]
        url_credentials = wizard.split("urls_creds()", 1)[1].split(
            "versions_menu()", 1
        )[0]
        self.assertNotIn("base64 -d", app_credentials + url_credentials)
        self.assertNotIn('controller.sscScanCentralCtrlToken="$token"', wizard)
        self.assertIn("--set-string controller.sscScanCentralCtrlToken=", wizard)
        for legacy_value in (
            "secrets.fortifyLicense=",
            "secrets.workerAuthToken=",
            "secrets.clientAuthToken=",
            "secrets.sscScanCentralCtrlSecret=",
        ):
            self.assertIn(legacy_value, wizard)
        self.assertNotIn("controller.sscScanCentralCtrlToken", sast)
        self.assertIn('read -rsp "Paste ControllerToken', wizard)
        self.assertIn("--patch-file /dev/stdin", wizard)
        self.assertIn("configured lab password (not displayed)", wizard)

    def test_controller_token_update_keeps_value_out_of_output_and_arguments(self) -> None:
        token = "synthetic-controller-secret"
        command = r'''
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            NAMESPACE=fortify
            HELM=fake_helm
            KUBECTL=fake_kubectl
            fake_helm() { return 0; }
            fake_kubectl() {
                if [[ "$*" == *" patch secret "* ]]; then cat >/dev/null; fi
                return 0
            }
            export -f fake_helm fake_kubectl
            configure_ssc_token
        '''
        with subprocess.Popen(
            ["bash", "-c", command, "token-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            stdout, stderr = process.communicate(token + "\n", timeout=10)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertNotIn(token, stdout + stderr)


if __name__ == "__main__":
    unittest.main()
