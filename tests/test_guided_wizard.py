"""Contracts for guided, express, and resumable deployment UX."""

from __future__ import annotations

import os
import tempfile
import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIZARD = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")


class GuidedWizardTests(unittest.TestCase):
    def run_wizard_functions(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        # Never depend on (or mutate) the developer/runner acknowledgement.
        # Guided entry points enforce the lab boundary, so acknowledge it
        # explicitly in a fresh configuration directory for every test.
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["XDG_CONFIG_HOME"] = str(Path(directory) / "config")
            environment["HOME"] = str(Path(directory) / "home")
            return subprocess.run(
                [
                    "bash",
                    "-c",
                    'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; '
                    "title() { :; }; sleep() { :; }; " + body,
                    "guided-test",
                    str(ROOT / "start_wizard.sh"),
                ],
                input="LAB\n" + user_input,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
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
        self.assertIn('guided_run_and_verify certs "Certs"', WIZARD)
        for operation in ("certs", "dashboard", "secrets", "mysql", "ssc", "dast"):
            self.assertIn(f"{operation})", WIZARD)

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

    def test_guided_entry_routes_existing_lab_to_resume_repair(self) -> None:
        self.assertIn("managed_releases_exist()", WIZARD)
        self.assertIn("Existing managed releases detected; opening Resume or repair", WIZARD)
        self.assertIn("fresh_deployment_guard()", WIZARD)

        result = self.run_wizard_functions(
            'managed_releases_exist() { return 0; }; '
            'press_any() { :; }; '
            'resume_repair() { printf "RESUME\\n"; }; '
            'guided_deployment_menu',
            "\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RESUME", result.stdout)
        self.assertIn("Existing managed releases detected", result.stdout)

    def test_preflight_allows_existing_releases_for_resume_flow(self) -> None:
        preflight_body = WIZARD.split("preflight_check()", 1)[1].split("deploy_step()", 1)[0]
        self.assertNotIn("Managed releases already exist", preflight_body)
        self.assertNotIn("helm", preflight_body.lower())

    def test_fresh_deploy_guard_refuses_existing_releases(self) -> None:
        result = self.run_wizard_functions(
            'managed_release_names() { printf "mysql\\nssc\\n"; }; fresh_deployment_guard',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Managed releases already exist", result.stderr)
        self.assertIn("Resume or repair", result.stderr)
        self.assertIn("existing release: mysql", result.stdout)

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

    def test_guided_lifecycle_registry_covers_every_step(self) -> None:
        for registry in (
            "GUIDED_STEP_TIMEOUT=",
            "GUIDED_STEP_MANUAL=",
            "GUIDED_STEP_PROBE=",
            "guided_step_index()",
            "guided_step_probe()",
            "guided_step_timeout()",
            "guided_wait_for_step()",
        ):
            self.assertIn(registry, WIZARD)

        result = self.run_wizard_functions(
            'printf "%s|%s|%s\n" "$(guided_step_probe mysql)" "$(guided_step_timeout mysql)" "$(guided_step_progress_message mysql)"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mysql_ready|600|Waiting for the MySQL StatefulSet", result.stdout)
        self.assertIn('openssl x509 -in "$SERVER_CERT" -noout', WIZARD)
        self.assertIn('keytool -list -keystore "$TRUSTSTORE"', WIZARD)


    def test_secrets_probe_handles_dotted_keys_and_reports_missing_detail(self) -> None:
        self.assertIn("GUIDED_STEP_TIMEOUT=(900 300 120 180 300 60", WIZARD)
        self.assertIn("secret_key_exists()", WIZARD)
        self.assertIn('go-template={{ index .data \\\"$key\\\" }}', WIZARD)
        self.assertNotIn('jsonpath={.data.${required_key//./', WIZARD)
        self.assertIn("secrets_missing_detail()", WIZARD)
        self.assertIn("Missing secret %s in namespace %s", WIZARD)
        self.assertIn("Missing key %s in secret fortify-secrets", WIZARD)
        self.assertIn("secrets) secrets_missing_detail", WIZARD)

        missing_secret = self.run_wizard_functions(
            'NAMESPACE=fortify; cluster_reachable() { return 0; }; '
            'resource_exists() { [ "$3" != tls ]; }; secrets_missing_detail'
        )
        self.assertEqual(missing_secret.returncode, 0, missing_secret.stderr)
        self.assertIn("Missing secret tls in namespace fortify", missing_secret.stdout)

        missing_key = self.run_wizard_functions(
            'NAMESPACE=fortify; cluster_reachable() { return 0; }; '
            'resource_exists() { return 0; }; '
            'secret_key_exists() { [ "$2" != fortify.license ]; }; secrets_missing_detail'
        )
        self.assertEqual(missing_key.returncode, 0, missing_key.stderr)
        self.assertIn("Missing key fortify.license in secret fortify-secrets", missing_key.stdout)

    def test_guided_run_waits_for_verification_after_operation(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(demo); GUIDED_STEP_LABEL=(Demo); '
            'GUIDED_STEP_OPTIONAL=(0); GUIDED_STEP_MANUAL=(0); GUIDED_STEP_TIMEOUT=(5); '
            'GUIDED_STEP_PROBE=(demo_ready); COMPLETE=0; RAN=0; '
            'demo_ready() { [ "$COMPLETE" -eq 1 ]; }; '
            'run_deployment_operation() { RAN=1; COMPLETE=1; }; '
            'guided_run_and_verify demo Demo; printf "RAN=%s STATE=%s\n" "$RAN" "$GUIDED_WAIT_LAST_STATE"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RAN=1 STATE=complete", result.stdout)

    def test_guided_run_does_not_advance_when_required_manual_step_incomplete(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(demo); GUIDED_STEP_LABEL=(Demo); '
            'GUIDED_STEP_OPTIONAL=(0); GUIDED_STEP_MANUAL=(1); GUIDED_STEP_TIMEOUT=(0); '
            'GUIDED_STEP_PROBE=(demo_ready); demo_ready() { return 1; }; '
            'run_deployment_operation() { :; }; guided_deployment',
            "r\n\nq\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Correct the issue, then choose Retry", result.stderr)


    def test_auto_advance_default_countdown_is_five_seconds(self) -> None:
        self.assertIn('GUIDED_AUTO_ADVANCE_DELAY="${GUIDED_AUTO_ADVANCE_DELAY:-5}"', WIZARD)

    def test_prerequisite_menu_shows_completion_indicators(self) -> None:
        self.assertIn("prereqs_status_table()", WIZARD)
        self.assertIn('"Host prerequisites: $ready/4 ready."', WIZARD)
        self.assertIn("All prerequisite indicators are complete", WIZARD)
        self.assertIn("Next missing: MicroK8s group access in this shell", WIZARD)
        self.assertIn("Restart wizard with microk8s group access", WIZARD)

    def test_prerequisite_probe_requires_microk8s_access(self) -> None:
        self.assertIn("microk8s_access_ready()", WIZARD)
        self.assertIn("id -nG | grep -qw microk8s", WIZARD)
        self.assertIn("microk8s status --wait-ready", WIZARD)
        self.assertIn("java_ready && docker_ready && mkcert_ready && microk8s_access_ready", WIZARD)

    def test_auto_advance_mode_can_complete_without_repeated_enter(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_AUTO_ADVANCE=1; GUIDED_AUTO_ADVANCE_DELAY=0; '
            'GUIDED_STEP_ID=(one two); GUIDED_STEP_LABEL=(One Two); '
            'GUIDED_STEP_OPTIONAL=(0 0); GUIDED_STEP_MANUAL=(0 0); GUIDED_STEP_TIMEOUT=(5 5); '
            'GUIDED_STEP_PROBE=(one_ready two_ready); one_ready() { return 0; }; two_ready() { return 0; }; '
            'guided_deployment',
            "\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Guided deployment complete", result.stdout)


    def test_wait_screen_redraws_without_full_clear_flash(self) -> None:
        self.assertIn("guided_wait_screen_enter()", WIZARD)
        self.assertIn("guided_wait_screen_render_start()", WIZARD)
        self.assertIn("guided_wait_screen_leave()", WIZARD)
        self.assertIn("printf '\\033[?25l'", WIZARD)
        self.assertIn("printf '\\033[H\\033[J'", WIZARD)
        self.assertIn("printf '\\033[?25h'", WIZARD)
        self.assertNotIn("trap guided_wait_screen_leave RETURN", WIZARD)

        wait_body = WIZARD.split("guided_wait_for_step()", 1)[1].split("wizard_deployment_plan()", 1)[0]
        self.assertNotIn("clear", wait_body)
        self.assertIn("guided_wait_screen_render_start", wait_body)
        self.assertIn("guided_wait_screen_leave", wait_body)

    def test_resume_labels_in_progress_work(self) -> None:
        self.assertIn("in progress", WIZARD)
        self.assertIn("guided_step_in_progress()", WIZARD)
        self.assertIn("Watch verification", WIZARD)
        self.assertIn("Probe:", WIZARD)
        self.assertIn("probe $probe is still failing", WIZARD)

    def test_failure_screen_can_create_sanitized_diagnostics(self) -> None:
        self.assertIn("guided_diagnostics_bundle()", WIZARD)
        self.assertIn("Create sanitized diagnostics bundle", WIZARD)
        self.assertIn("d. Diagnostics", WIZARD)
        self.assertIn("r. Retry operation", WIZARD)
        self.assertIn('GUIDED_WAIT_LAST_STATE="retry"', WIZARD)



    def test_guided_preflight_contracts_are_mode_specific(self) -> None:
        self.assertIn('GUIDED_PREFLIGHT_MODE_ID=("fresh" "resume" "component")', WIZARD)
        self.assertIn("guided_preflight_contract()", WIZARD)
        self.assertIn("fresh: read-only preflight plus empty managed-release guard", WIZARD)
        self.assertIn("resume: read-only preflight; existing managed releases are expected", WIZARD)
        self.assertIn("component: read-only preflight; existing managed releases are allowed", WIZARD)

        result = self.run_wizard_functions(
            'guided_preflight_contract fresh; '
            'guided_preflight_contract resume; '
            'guided_preflight_contract component'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fresh: read-only preflight plus empty managed-release guard", result.stdout)
        self.assertIn("resume: read-only preflight; existing managed releases are expected", result.stdout)
        self.assertIn("component: read-only preflight; existing managed releases are allowed", result.stdout)

    def test_guided_mode_banner_and_context_text_are_rendered(self) -> None:
        self.assertIn("guided_mode_context_text()", WIZARD)
        self.assertIn("Guided mode: fresh deployment", WIZARD)
        self.assertIn("Guided mode: resume or repair", WIZARD)
        self.assertIn("Guided mode: component repair", WIZARD)
        self.assertIn("printf '\\n  %s\\n' \"$(guided_mode_context_text fresh)\"", WIZARD)
        self.assertIn("printf '\\n  %s\\n' \"$(guided_mode_context_text \"$GUIDED_MODE_CONTEXT\")\"", WIZARD)
        self.assertIn("GUIDED_MODE_CONTEXT=resume", WIZARD)

        result = self.run_wizard_functions(
            'guided_mode_context_text fresh; '
            'guided_mode_context_text resume; '
            'guided_mode_context_text component; '
            'GUIDED_MODE_CONTEXT=resume; guided_mode_context_text'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fresh deployment", result.stdout)
        self.assertEqual(result.stdout.count("resume or repair"), 2)
        self.assertIn("component repair", result.stdout)

    def test_guided_why_pending_detail_covers_state_machine_steps(self) -> None:
        self.assertIn("guided_step_why_pending()", WIZARD)
        self.assertIn("Why pending:", WIZARD)
        progress_body = WIZARD.split("guided_step_progress_message()", 1)[1].split(
            "guided_step_why_pending()", 1
        )[0]
        for step in (
            "prereqs", "inputs", "preflight", "certs", "dashboard", "secrets",
            "mysql", "postgresql", "ssc", "lim", "sast", "dast", "configure",
        ):
            with self.subTest(step=step):
                self.assertIn(f"{step})", progress_body)

        pending = self.run_wizard_functions(
            'NAMESPACE=fortify; DOMAIN=lab.test; '
            'guided_step_complete() { return 1; }; '
            'guided_step_in_progress() { return 1; }; '
            'cluster_reachable() { return 1; }; '
            'guided_step_why_pending secrets; guided_step_why_pending configure'
        )
        self.assertEqual(pending.returncode, 0, pending.stderr)
        self.assertIn("Cluster is not reachable while checking Kubernetes Secrets", pending.stdout)
        self.assertIn("Hostname ssc.lab.test", pending.stdout)

        complete = self.run_wizard_functions(
            'guided_step_complete() { return 0; }; guided_step_why_pending mysql'
        )
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertIn("Step is complete; no pending action is required", complete.stdout)

    def test_guided_repair_recommendations_are_step_specific(self) -> None:
        self.assertIn("guided_repair_recommendation()", WIZARD)
        self.assertIn('note "$(guided_repair_recommendation "${GUIDED_STEP_ID[$start]}")"', WIZARD)
        self.assertIn("Repair recommendation: repair MySQL first, then retry SSC", WIZARD)
        self.assertIn("Data risk: rotating SSC secret.key", WIZARD)
        self.assertIn("Avoid destructive cleanup unless a step explicitly says data will be deleted", WIZARD)

        result = self.run_wizard_functions(
            'guided_repair_recommendation ssc; '
            'guided_repair_recommendation secrets; '
            'guided_repair_recommendation unknown'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repair MySQL first", result.stdout)
        self.assertIn("rotating SSC secret.key", result.stdout)
        self.assertIn("Avoid destructive cleanup", result.stdout)


    def test_doctor_command_is_read_only_and_secret_safe(self) -> None:
        self.assertIn("./start_wizard.sh doctor", WIZARD)
        self.assertIn("wizard_doctor()", WIZARD)
        self.assertIn("wizard_doctor_load_env()", WIZARD)
        doctor_body = WIZARD.split("wizard_doctor()", 1)[1].split("managed_release_names()", 1)[0]
        self.assertNotIn("bootstrap_env", doctor_body)
        self.assertIn("operational_doctor_compact_health_summary", doctor_body)
        self.assertIn("operational_doctor_http_status", doctor_body)
        self.assertIn("Guided readiness", doctor_body)
        self.assertIn("operational_cluster_available || unavailable=1", doctor_body)
        self.assertIn("return 2", doctor_body)
        self.assertIn("Step type:", WIZARD)

    def test_live_plan_uses_guided_registry_and_labels_impact(self) -> None:
        self.assertIn("wizard_deployment_plan()", WIZARD)
        self.assertIn('for idx in "${!GUIDED_STEP_ID[@]}"', WIZARD)
        self.assertIn("GUIDED_STEP_DURATION=", WIZARD)
        self.assertIn("GUIDED_STEP_IMPACT=", WIZARD)
        self.assertIn("persistent-data deletion is a separate expert action", WIZARD)


if __name__ == "__main__":
    unittest.main()
