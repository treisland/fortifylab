"""Contracts for guided, express, and resumable deployment UX."""

from __future__ import annotations

import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIZARD = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")


class GuidedWizardTests(unittest.TestCase):
    def run_wizard_functions(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; '
                "title() { :; }; sleep() { :; }; " + body,
                "guided-test",
                str(ROOT / "start_wizard.sh"),
            ],
            input=user_input,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_main_menu_preserves_all_deployment_personas(self) -> None:
        for label in (
            "Guided deployment (recommended)",
            "Express deployment",
            "Resume or repair deployment",
            "Manage individual components (expert)",
            "Kubernetes Dashboard access",
            "Diagnostics / live status",
            "Advanced setup and configuration",
        ):
            self.assertIn(label, WIZARD)

    def test_guided_and_express_share_one_operation_dispatcher(self) -> None:
        self.assertIn("run_deployment_operation()", WIZARD)
        self.assertIn('run_deployment_operation "$id"', WIZARD)
        for operation in ("certs", "dashboard", "secrets", "mysql", "ssc", "dast"):
            self.assertIn(f"run_deployment_operation {operation}", WIZARD)

    def test_guided_flow_supports_failure_retry_and_safe_quit(self) -> None:
        self.assertIn('echo "  t. Retry"', WIZARD)
        self.assertIn("Correct the issue, then choose Retry.", WIZARD)
        self.assertIn("Quit safely", WIZARD)
        self.assertIn("No wizard state or secrets were written", WIZARD)

        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(demo); GUIDED_STEP_LABEL=(Demo); '
            'GUIDED_STEP_OPTIONAL=(0); GUIDED_STEP_HELP=(Help); '
            'guided_step_complete() { return 1; }; '
            'run_deployment_operation() { return 1; }; guided_deployment',
            "r\n\nq\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("choose Retry", result.stderr)
        self.assertIn("No wizard state or secrets were written", result.stdout)

    def test_successful_operation_advances_and_finishes(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(demo); GUIDED_STEP_LABEL=(Demo); '
            'GUIDED_STEP_OPTIONAL=(0); GUIDED_STEP_HELP=(Help); COMPLETE=0; '
            'guided_step_complete() { [ "$COMPLETE" -eq 1 ]; }; '
            'run_deployment_operation() { COMPLETE=1; }; guided_deployment',
            "r\n\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Guided deployment complete", result.stdout)

    def test_resume_is_live_derived_and_starts_at_first_required_gap(self) -> None:
        self.assertIn("State is derived from current files and Kubernetes", WIZARD)
        self.assertIn('! guided_step_complete "$id"', WIZARD)
        self.assertIn('guided_deployment "$start"', WIZARD)
        self.assertNotIn("wizard-state", WIZARD.lower())

        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(done gap later); GUIDED_STEP_LABEL=(Done Gap Later); '
            'GUIDED_STEP_OPTIONAL=(0 0 0); '
            'guided_step_complete() { [ "$1" = done ]; }; '
            'press_any() { :; }; guided_deployment() { printf "START=%s\\n" "$1"; }; '
            'resume_repair'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("START=1", result.stdout)

    def test_optional_skip_is_explicit_and_required_skip_is_rejected(self) -> None:
        self.assertIn("GUIDED_STEP_OPTIONAL=(1 0 0 0 0 0 0 0 0 0 0 0 1)", WIZARD)
        self.assertIn("Skip optional step", WIZARD)
        self.assertIn("is required and cannot be skipped", WIZARD)

        optional = self.run_wizard_functions(
            'GUIDED_STEP_ID=(demo); GUIDED_STEP_LABEL=(Demo); '
            'GUIDED_STEP_OPTIONAL=(1); GUIDED_STEP_HELP=(Help); '
            'guided_step_complete() { return 1; }; guided_deployment',
            "s\n\n",
        )
        self.assertEqual(optional.returncode, 0, optional.stderr)
        self.assertIn("Skipped optional step", optional.stdout)

        required = self.run_wizard_functions(
            'GUIDED_STEP_ID=(demo); GUIDED_STEP_LABEL=(Demo); '
            'GUIDED_STEP_OPTIONAL=(0); GUIDED_STEP_HELP=(Help); '
            'guided_step_complete() { return 1; }; guided_deployment',
            "s\nq\n",
        )
        self.assertEqual(required.returncode, 0, required.stderr)
        self.assertIn("required and cannot be skipped", required.stderr)

    def test_status_rendering_does_not_dispatch_mutations(self) -> None:
        status_body = WIZARD.split("guided_step_status()", 1)[1].split(
            "run_deployment_operation()", 1
        )[0]
        for mutation in ("apply", "upgrade", "create-certs", "create-secrets"):
            self.assertNotIn(mutation, status_body)

    def test_live_plan_uses_guided_registry_and_labels_impact(self) -> None:
        self.assertIn("wizard_deployment_plan()", WIZARD)
        self.assertIn('for idx in "${!GUIDED_STEP_ID[@]}"', WIZARD)
        self.assertIn("GUIDED_STEP_DURATION=", WIZARD)
        self.assertIn("GUIDED_STEP_IMPACT=", WIZARD)
        self.assertIn("persistent-data deletion is a separate expert action", WIZARD)


if __name__ == "__main__":
    unittest.main()
