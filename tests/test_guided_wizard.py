"""Contracts for guided, express, and resumable deployment UX."""

from __future__ import annotations

import os
import tempfile
import unittest
import subprocess
from pathlib import Path

from tests.wizard_source import read_wizard_source


ROOT = Path(__file__).resolve().parents[1]
WIZARD = read_wizard_source(ROOT)


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

    def make_lab_cert(self, directory: Path, name: str = "tls") -> tuple[Path, Path]:
        cert = directory / f"{name}.crt"
        key = directory / f"{name}.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=ssc.example.test",
                "-addext",
                "subjectAltName=DNS:ssc.example.test,DNS:lim.example.test,DNS:sast.example.test,DNS:dast.example.test,DNS:dashboard.example.test",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return cert, key

    def test_main_menu_preserves_all_deployment_personas(self) -> None:
        for label in (
            "Guided deployment (recommended)",
            "Express deployment",
            "Resume or repair deployment",
            "Flight Plans and upgrades",
            "Manage individual components (expert)",
            "Sample applications",
            "Kubernetes Dashboard access",
            "Diagnostics / live status",
            "Advanced setup and configuration",
            "Lab lifecycle controls",
            "Tools and FCLI readiness",
            "Runbook Library",
        ):
            self.assertIn(label, WIZARD)

    def test_first_time_welcome_menu_does_not_duplicate_main_menu_actions(self) -> None:
        body = WIZARD.split("fortifylab_first_time_welcome_menu() {", 1)[1].split("# ============================================================\n# Main menu", 1)[0]
        self.assertNotIn("Start guided setup", body)
        self.assertNotIn("Choose deployment profile", body)
        self.assertNotIn("Open Help Center", body)
        self.assertNotIn("Advanced setup and configuration", body)
        self.assertNotIn("guided_setup_menu", body)
        self.assertNotIn("guided_profile_menu", body)
        self.assertNotIn("advanced_menu", body)
        self.assertIn("main menu includes Initial setup and readiness", body)

    def test_first_time_welcome_content_orients_beginners_without_secrets(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'mkdir -p "$tmp/scripts/lib" "$tmp/certs"; printf "DOMAIN=lab.example\n" > "$ENV_FILE"; '
            'printf "%s\n" "fortify_resolve_license_file() { return 1; }" > "$tmp/scripts/lib/fortify-license.sh"; '
            'DOMAIN=lab.example; GUIDED_DEPLOYMENT_PROFILE_LABEL="SAST full with SSC"; FORTIFYLAB_VERSION=vtest; '
            'fortifylab_first_time_welcome_content'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (
            "FortifyLab vtest",
            "ready-to-scan Fortify training lab",
            "Recommended path",
            "Choose the deployment profile",
            "Run this wizard as your normal user, not with sudo",
            "not a production architecture",
            "Sample applications, when installed, are intentionally vulnerable",
            "DAST workflows require ScanCentral DAST and WebInspect licenses in LIM",
            "Helpful locations",
            ".env.backups",
            "Wizard log",
            "Quick environment snapshot",
            "Domain:          lab.example",
            "Profile:         SAST full with SSC",
        ):
            self.assertIn(expected, result.stdout)
        self.assertNotIn("DEFAULT_PASS", result.stdout)
        self.assertNotIn("ControllerToken", result.stdout)

    def test_sample_apps_have_visible_top_level_menu(self) -> None:
        self.assertIn('4)  versions_menu ;;', WIZARD)
        self.assertIn('6)  sample_apps_menu ;;', WIZARD)
        self.assertIn('sample_apps_menu()', WIZARD)
        self.assertIn('apps_menu_for_scope "samples"', WIZARD)
        self.assertIn('title "$heading"', WIZARD)
        self.assertIn('visible_indices[$visible]="$i"', WIZARD)
        self.assertIn('app_action_menu "${visible_indices[$choice]}"', WIZARD)
        self.assertIn('Intentionally vulnerable lab targets', WIZARD)
        self.assertIn('Select one of the sample application numbers shown above.', WIZARD)

    def test_sample_apps_menu_uses_local_numbering(self) -> None:
        result = self.run_wizard_functions(
            'APP_LABEL=(MySQL PostgreSQL SSC LIM SAST DAST "Juice Shop" WebGoat DVWA); '
            'APP_PODS=(mysql postgresql ssc lim sast dast sample-juice-shop sample-webgoat sample-dvwa); '
            'APP_SAMPLE=(0 0 0 0 0 0 1 1 1); '
            'title() { printf "TITLE:%s\n" "$*"; }; '
            'app_status() { printf "not deployed"; }; '
            'fortify_lab_show_action_warning() { :; }; '
            'ask() { read -r "$1"; }; '
            'sample_apps_menu',
            user_input='r\n',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('  1   Juice Shop', result.stdout)
        self.assertIn('  2   WebGoat', result.stdout)
        self.assertIn('  3   DVWA', result.stdout)
        self.assertNotIn('  7   Juice Shop', result.stdout)

    def test_guided_and_express_share_one_operation_dispatcher(self) -> None:
        self.assertIn("run_deployment_operation()", WIZARD)
        self.assertIn('run_deployment_operation "$id"', WIZARD)
        self.assertIn('guided_run_and_verify "$step"', WIZARD)
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
            'guided_step_live_complete() { [ "$COMPLETE" -eq 1 ]; }; '
            'run_deployment_operation() { COMPLETE=1; }; guided_deployment',
            "r\n\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Congratulations, FortifyLab is ready", result.stdout)


    def test_completion_screen_and_credential_handoff_are_safe_by_default(self) -> None:
        for expected in (
            "Access & credentials",
            "Reveal one credential",
            "Type REVEAL to display this value once",
            "The wizard will not write this value to logs, diagnostics, .env",
            "refer to the SSC documentation for the default password",
            "FortifyLab does not store or display that vendor default password",
            "Credential availability",
            "Certificate trust",
            "First scan handoff",
            "docs/examples/first-scan",
        ):
            self.assertIn(expected, WIZARD)
        self.assertNotIn("see initial admin password in SSC startup logs", WIZARD)
        self.assertNotIn("search the log for 'admin'", WIZARD)


    def test_completion_screen_links_fcli_readiness_handoff(self) -> None:
        self.assertIn("Tools and FCLI readiness", WIZARD)
        completion_menu = WIZARD.split("guided_completion_screen()", 1)[1].split("guided_deployment_menu()", 1)[0]
        self.assertIn("2. Tools and FCLI readiness", completion_menu)
        self.assertIn("2) fcli_tools_menu", completion_menu)

    def test_completion_screen_links_first_scan_handoff(self) -> None:
        self.assertIn("First scan handoff", WIZARD)
        self.assertIn("first_scan_handoff()", WIZARD)
        completion_menu = WIZARD.split("guided_completion_screen()", 1)[1].split("guided_deployment_menu()", 1)[0]
        self.assertIn("3. First scan handoff", completion_menu)
        self.assertIn("3) first_scan_handoff", completion_menu)

    def test_completion_screen_lists_profile_status_and_next_actions(self) -> None:
        result = self.run_wizard_functions(
            'DOMAIN=fortifydemo.test; NAMESPACE=fortify; KUBECTL=kube; '
            'SSC_URL=https://ssc.fortifydemo.test; LIM_URL=https://lim.fortifydemo.test; '
            'SCSAST_CTRL_URL=https://sast.fortifydemo.test/scancentral-ctrl; SCDAST_URL=https://dast.fortifydemo.test; '
            'GUIDED_DEPLOYMENT_PROFILE_LABEL="SAST Full"; GUIDED_DEPLOYMENT_COMPONENTS="ssc,sast_controller,sast_sensor"; '
            'GUIDED_STEP_ID=(dashboard ssc sast_controller sast_sensor); '
            'GUIDED_STEP_LABEL=(Dashboard SSC SASTController SASTSensor); '
            'GUIDED_STEP_OPTIONAL=(0 0 0 0); GUIDED_STEP_HELP=(Help Help Help Help); COMPLETE=0; '
            'cluster_reachable() { return 0; }; secret_key_exists() { return 1; }; '
            'app_status() { printf "1/1 running"; }; guided_step_live_status() { printf complete; }; '
            'guided_step_complete() { [ "$COMPLETE" -eq 1 ]; }; '
            'guided_step_live_complete() { [ "$COMPLETE" -eq 1 ]; }; '
            'run_deployment_operation() { COMPLETE=1; }; guided_deployment',
            "r\nn\nn\nn\nr\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Congratulations, FortifyLab is ready", result.stdout)
        self.assertIn("Profile: SAST Full", result.stdout)
        self.assertIn("SSC", result.stdout)
        self.assertIn("ScanCentral SAST", result.stdout)
        self.assertIn("https://ssc.fortifydemo.test", result.stdout)
        self.assertIn("create an SSC ControllerToken", result.stdout)

    def test_resume_is_live_derived_and_starts_at_first_required_gap(self) -> None:
        self.assertIn("State is derived from current files and Kubernetes", WIZARD)
        self.assertIn('! guided_step_live_complete "$id"', WIZARD)
        self.assertIn('guided_deployment "$start"', WIZARD)
        self.assertIn("Checking deployment state", WIZARD)
        self.assertIn("guided_collect_step_statuses", WIZARD)
        self.assertIn("guided_cached_step_status", WIZARD)
        self.assertNotIn("wizard-state", WIZARD.lower())

        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(done gap later); GUIDED_STEP_LABEL=(Done Gap Later); '
            'GUIDED_STEP_OPTIONAL=(0 0 0); '
            'guided_step_complete() { [ "$1" = done ]; }; '
            'press_any() { :; }; guided_apply_deployment_profile() { :; }; guided_deployment() { printf "START=%s\\n" "$1"; }; '
            'resume_repair'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("START=1", result.stdout)
        self.assertIn("[ 1/ 3] Done", result.stdout)
        self.assertIn("Deployment state", result.stdout)

    def test_resume_status_collection_shows_progress_before_final_table(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_STEP_ID=(one two); GUIDED_STEP_LABEL=(One Two); '
            'GUIDED_STEP_OPTIONAL=(0 0); GUIDED_STEP_MANUAL=(0 0); '
            'guided_step_live_state() { [ "$1" = one ] && printf complete || printf pending; }; '
            'guided_step_live_complete() { [ "$1" = one ]; }; '
            'press_any() { :; }; guided_apply_deployment_profile() { :; }; guided_deployment() { :; }; resume_repair'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Checking deployment state", result.stdout)
        self.assertIn("[ 1/ 2] One", result.stdout)
        self.assertIn("[ 2/ 2] Two", result.stdout)
        self.assertIn("complete", result.stdout)
        self.assertIn("pending", result.stdout)
        self.assertNotIn("checking...", result.stdout)
        self.assertIn("Deployment state", result.stdout)


    def test_resume_treats_manually_deployed_sast_pods_as_complete(self) -> None:
        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; '
            'GUIDED_STEP_ID=(sast dast); '
            'GUIDED_STEP_LABEL=("ScanCentral SAST" "ScanCentral DAST"); '
            'GUIDED_STEP_OPTIONAL=(0 0); GUIDED_STEP_MANUAL=(0 0); '
            'cluster_reachable() { return 0; }; '
            'kube() { case "$*" in '
            '"-n fortify get pods --no-headers") printf "scancentral-sast-controller-0 1/1 Running 0 1m\nscancentral-sast-sensor-0 1/1 Running 0 1m\n" ;; '
            '*"scancentral-sast-controller"*"jsonpath={.spec.replicas}"*) printf 1 ;; '
            '*"scancentral-sast-controller"*"jsonpath={.status.readyReplicas}"*) printf 1 ;; '
            '*"scancentral-sast-sensor"*"jsonpath={.spec.replicas}"*) printf 1 ;; '
            '*"scancentral-sast-sensor"*"jsonpath={.status.readyReplicas}"*) printf 1 ;; '
            '*) return 1 ;; '
            'esac; }; '
            'press_any() { :; }; guided_apply_deployment_profile() { :; }; guided_deployment() { printf "START=%s\n" "$1"; }; '
            'resume_repair'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ScanCentral SAST", result.stdout)
        self.assertIn("complete", result.stdout)
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

    def test_preflight_resource_warnings_identify_low_ram_and_disk(self) -> None:
        result = self.run_wizard_functions(
            'preflight_memory_gib() { printf 8; }; '
            'preflight_disk_gib() { printf 20; }; '
            'preflight_resource_warnings',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Host memory is 8 GiB", result.stdout)
        self.assertIn("Free disk is 20 GiB", result.stdout)

    def test_low_resource_preflight_can_continue_with_interactive_confirmation(self) -> None:
        result = self.run_wizard_functions(
            'preflight_memory_gib() { printf 8; }; '
            'preflight_disk_gib() { printf 20; }; '
            'preflight_can_prompt_for_low_resources() { return 0; }; '
            'confirm() { return 0; }; '
            'preflight_confirm_low_resources',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Resource warnings do not block", result.stderr)

    def test_low_resource_preflight_refuses_noninteractive_without_override(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_AUTO_ADVANCE=1; '
            'preflight_memory_gib() { printf 8; }; '
            'preflight_disk_gib() { printf 20; }; '
            'preflight_confirm_low_resources',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FORTIFY_ALLOW_LOW_RESOURCES=1", result.stderr)

    def test_low_resource_preflight_allows_noninteractive_env_override(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_AUTO_ADVANCE=1; FORTIFY_ALLOW_LOW_RESOURCES=1; '
            'preflight_memory_gib() { printf 8; }; '
            'preflight_disk_gib() { printf 20; }; '
            'preflight_confirm_low_resources',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FORTIFY_ALLOW_LOW_RESOURCES=1", result.stdout)

    def test_preflight_readiness_does_not_block_on_low_ram_or_disk(self) -> None:
        result = self.run_wizard_functions(
            'mkdir -p "$HOME/.docker"; printf x > "$HOME/.docker/config.json"; '
            'prereqs_complete() { return 0; }; inputs_complete() { return 0; }; '
            'cluster_reachable() { return 0; }; microk8s() { return 0; }; '
            'KUBECTL=mock_kubectl; mock_kubectl() { return 0; }; DOMAIN=demo.test; NAMESPACE=fortify; DEFAULT_PASS=demo; '
            'FORTIFY_FLIGHT_PLAN=fortify-26.2; FORTIFY_SSC_CHART_VERSION=1; FORTIFY_SSC_IMAGE_TAG=1; '
            'FORTIFY_SCSAST_CHART_VERSION=1; '
            'preflight_memory_gib() { printf 4; }; preflight_disk_gib() { printf 4; }; '
            'preflight_inputs_complete',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fresh_deploy_guard_refuses_existing_releases(self) -> None:
        result = self.run_wizard_functions(
            'managed_release_names() { printf "mysql\\nssc\\n"; }; fresh_deployment_guard',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Managed releases already exist", result.stderr)
        self.assertIn("Resume or repair", result.stderr)
        self.assertIn("existing release: mysql", result.stdout)

    def test_gitignore_covers_wizard_env_backups(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            ".env.backups/",
            ".env.*.bak",
            ".env.bak",
            ".env.tmp",
            ".env.rollback",
        ):
            self.assertIn(pattern, gitignore)

    def test_env_apply_preserves_comments_unknown_keys_and_writes_metadata(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "# keep this comment" "export DOMAIN=\"old.test\"" "CUSTOM_FLAG=yes" "export DEFAULT_PASS=\"old\"" >"$ENV_FILE"; '
            'env_apply_updates wizard-test "DOMAIN=new.test" "DEFAULT_PASS=p@ss&word"; '
            'cat "$ENV_FILE"; printf "META\n"; cat "$ENV_BACKUP_DIR"/.env.*.meta',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# keep this comment", result.stdout)
        self.assertIn("CUSTOM_FLAG=yes", result.stdout)
        self.assertIn("export DOMAIN='new.test'", result.stdout)
        self.assertIn("export DEFAULT_PASS='p@ss&word'", result.stdout)
        self.assertIn("reason=wizard-test", result.stdout)
        self.assertIn("changed_keys=DOMAIN,DEFAULT_PASS", result.stdout)

    def test_env_rollback_last_restores_prior_env(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=\"old.test\"" >"$ENV_FILE"; '
            'env_apply_updates first "DOMAIN=new.test" >/dev/null; '
            'env_rollback_last >/dev/null; '
            'source "$ENV_FILE"; printf "DOMAIN=%s\n" "$DOMAIN"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DOMAIN=old.test", result.stdout)

    def test_configuration_editor_menu_uses_sectioned_operator_labels(self) -> None:
        menu = WIZARD.split("edit_env()", 1)[1].split("ask choice", 1)[0]
        for expected in (
            "Lab Settings",
            "Kubernetes namespace",
            "Change lab domain and derived URLs",
            "Deployment Settings",
            "Deployment versions and Flight Plans",
            "Credentials, users, and passwords",
            "Advanced service URLs",
            "Validation and Repair",
            "Validate configuration",
            "Repair derived URLs from domain",
            "Certificates and Trust",
            "Export root CA and trust instructions",
            "Backups and Advanced",
        ):
            self.assertIn(expected, menu)
        for retired in (
            "Lab identity and domain",
            "Image/chart versions",
            "  2. URLs",
            "Configuration diagnostics",
            "mkcert root CA export and trust help",
        ):
            self.assertNotIn(retired, menu)

    def test_configuration_editor_namespace_option_does_not_edit_domain(self) -> None:
        result = self.run_wizard_functions(
            "tmp=$(mktemp -d); FORTIFY_HOME_K8S=\"$tmp\"; ENV_FILE=\"$tmp/.env\"; ENV_BACKUP_DIR=\"$tmp/.env.backups\"; "
            "printf \"%s\\n\" \"export NAMESPACE=\\\"oldns\\\"\" \"export DOMAIN=\\\"old.test\\\"\" >\"$ENV_FILE\"; "
            "press_any() { :; }; "
            "read -r _lab_ack; env_guided_section_editor \"Kubernetes namespace\" identity; "
            "source \"$ENV_FILE\"; printf \"NAMESPACE=%s DOMAIN=%s\n\" \"$NAMESPACE\" \"$DOMAIN\"",
            user_input="1\nnewns\na\ny\nn\n\nr\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NAMESPACE=newns DOMAIN=old.test", result.stdout)
        self.assertNotIn("DOMAIN [old.test]", result.stdout)


    def test_guided_setup_stages_domain_and_can_cancel_without_writing(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=old.test" >"$ENV_FILE"; source "$ENV_FILE"; '
            'read -r _lab_ack; guided_setup_edit_step 1; setup_apply_pending; source "$ENV_FILE"; '
            'printf "DOMAIN=%s PENDING=%s\n" "$DOMAIN" "${#SETUP_PENDING_UPDATES[@]}"',
            user_input="new.test\nn\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Domain and derived URL changes staged", result.stdout)
        self.assertIn("Setup changes cancelled", result.stdout)
        self.assertIn("DOMAIN=old.test", result.stdout)

    def test_guided_setup_stages_external_license_path_and_applies_to_env(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); external="$tmp/customer/fortify.license"; mkdir -p "$(dirname "$external")"; '
            'printf "synthetic-license" >"$external"; FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; '
            'ENV_BACKUP_DIR="$tmp/lab/.env.backups"; mkdir -p "$FORTIFY_HOME_K8S"; printf "export DOMAIN=old.test\n" >"$ENV_FILE"; '
            'source "$ENV_FILE"; read -r _lab_ack; answers=(1 "$external" b); '
            'ask() { local __target="$1"; shift || true; printf -v "$__target" "%s" "${answers[0]}"; answers=("${answers[@]:1}"); }; '
            'setup_license_assistant; setup_review_pending; setup_apply_pending <<<"y" >/dev/null; '
            'source "$ENV_FILE"; printf "LICENSE=%s\n" "$FORTIFY_LICENSE_FILE"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("External Fortify license path staged", result.stdout)
        self.assertIn("FORTIFY_LICENSE_FILE", result.stdout)
        self.assertIn("LICENSE=", result.stdout)
        self.assertIn("/customer/fortify.license", result.stdout)

    def test_guided_setup_rejects_missing_external_license_without_pending_change(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; ENV_BACKUP_DIR="$tmp/lab/.env.backups"; '
            'mkdir -p "$FORTIFY_HOME_K8S"; printf "export DOMAIN=old.test\n" >"$ENV_FILE"; source "$ENV_FILE"; '
            'read -r _lab_ack; answers=(1 /missing/fortify.license b); '
            'ask() { local __target="$1"; shift || true; printf -v "$__target" "%s" "${answers[0]}"; answers=("${answers[@]:1}"); }; '
            'setup_license_assistant; printf "PENDING=%s\n" "${#SETUP_PENDING_UPDATES[@]}"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("missing, unreadable, or empty", combined)
        self.assertIn("PENDING=0", result.stdout)

    def test_guided_setup_stages_byo_tls_paths_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cert, key = self.make_lab_cert(Path(directory))
            result = self.run_wizard_functions(
                f'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; ENV_BACKUP_DIR="$tmp/lab/.env.backups"; '
                f'mkdir -p "$FORTIFY_HOME_K8S"; printf "export DOMAIN=example.test\n" >"$ENV_FILE"; source "$ENV_FILE"; '
                f'DOMAIN=example.test; SSC=ssc.example.test; LIM=lim.example.test; SCSAST=sast.example.test; SCDAST=dast.example.test; '
                f'read -r _lab_ack; answers=(2 "{cert}" "{key}" "{cert}" b); '
                f'ask() {{ local __target="$1"; shift || true; printf -v "$__target" "%s" "${{answers[0]}}"; answers=("${{answers[@]:1}}"); }}; '
                f'setup_tls_assistant; setup_review_pending; setup_apply_pending <<<"y" >/dev/null; source "$ENV_FILE"; '
                f'printf "MODE=%s CERT=%s KEY=%s CA=%s\n" "$FORTIFY_TLS_MODE" "$FORTIFY_BYO_TLS_CERT" "$FORTIFY_BYO_TLS_KEY" "$FORTIFY_BYO_TLS_CA_CERT"',
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BYO TLS certificate, key, and CA chain staged", result.stdout)
        self.assertIn("FORTIFY_TLS_MODE", result.stdout)
        self.assertIn("MODE=byo", result.stdout)
        self.assertIn(str(cert), result.stdout)
        self.assertNotIn("PRIVATE KEY", result.stdout + result.stderr)

    def test_guided_setup_rejects_mismatched_byo_tls_key_without_pending_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmpdir = Path(directory)
            cert, _key = self.make_lab_cert(tmpdir)
            _other_cert, other_key = self.make_lab_cert(tmpdir, "other")
            result = self.run_wizard_functions(
                f'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; ENV_BACKUP_DIR="$tmp/lab/.env.backups"; '
                f'mkdir -p "$FORTIFY_HOME_K8S"; printf "export DOMAIN=example.test\n" >"$ENV_FILE"; source "$ENV_FILE"; '
                f'DOMAIN=example.test; SSC=ssc.example.test; LIM=lim.example.test; SCSAST=sast.example.test; SCDAST=dast.example.test; '
                f'read -r _lab_ack; answers=(2 "{cert}" "{other_key}" "{cert}" b); '
                f'ask() {{ local __target="$1"; shift || true; printf -v "$__target" "%s" "${{answers[0]}}"; answers=("${{answers[@]:1}}"); }}; '
                f'setup_tls_assistant; printf "PENDING=%s\n" "${{#SETUP_PENDING_UPDATES[@]}}"',
            )
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("do not match", combined)
        self.assertIn("BYO TLS inputs did not validate", combined)
        self.assertIn("PENDING=0", result.stdout)
        self.assertNotIn("PRIVATE KEY", combined)

    def test_guided_setup_tls_status_explains_trust_and_next_actions(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; ENV_BACKUP_DIR="$tmp/lab/.env.backups"; '
            'mkdir -p "$FORTIFY_HOME_K8S"; DOMAIN=example.test; FORTIFY_TLS_MODE=mkcert; read -r _lab_ack; setup_tls_status'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("Purpose", "Current configuration", "Verification", "Impact", "Recommended next action", "Browser trust is client-side", "fcli trust"):
            self.assertIn(expected, result.stdout)

    def test_guided_setup_mkcert_mode_stages_tls_mode_without_private_key_copy(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; ENV_BACKUP_DIR="$tmp/lab/.env.backups"; '
            'mkdir -p "$FORTIFY_HOME_K8S"; printf "export FORTIFY_TLS_MODE=byo\nexport FORTIFY_BYO_TLS_KEY=/private/key.pem\n" >"$ENV_FILE"; source "$ENV_FILE"; '
            'read -r _lab_ack; answers=(1 b); ask() { local __target="$1"; shift || true; printf -v "$__target" "%s" "${answers[0]}"; answers=("${answers[@]:1}"); }; '
            'setup_tls_assistant; setup_review_pending',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mkcert TLS mode staged", result.stdout)
        self.assertIn("FORTIFY_TLS_MODE", result.stdout)
        self.assertIn("FORTIFY_BYO_TLS_KEY", result.stdout)
        self.assertNotIn("PRIVATE KEY", result.stdout + result.stderr)

    def test_guided_setup_applies_staged_domain_with_backup(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=old.test" >"$ENV_FILE"; source "$ENV_FILE"; '
            'read -r _lab_ack; guided_setup_edit_step 1; setup_apply_pending >/dev/null; source "$ENV_FILE"; '
            'printf "DOMAIN=%s BACKUPS=%s\n" "$DOMAIN" "$(find "$ENV_BACKUP_DIR" -name ".env.*.bak" | wc -l)"',
            user_input="new.test\ny\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DOMAIN=new.test", result.stdout)
        self.assertIn("BACKUPS=1", result.stdout)

    def test_setup_readiness_score_and_profile_preview_are_profile_aware(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=valid.test" >"$ENV_FILE"; FORTIFY_DEPLOYMENT_PROFILE=sast_full; '
            'env_config_valid() { return 0; }; inputs_complete() { return 0; }; setup_license_ready() { return 0; }; setup_docker_auth_ready() { return 0; }; '
            'setup_regcred_ready() { return 1; }; certs_ready() { return 0; }; setup_root_ca_exported() { return 0; }; '
            'setup_fcli_trust_ready() { return 1; }; cluster_reachable() { return 1; }; '
            'printf "SCORE=%s\n" "$(setup_readiness_score)"; setup_profile_preview sast_full',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SCORE=8/11", result.stdout)
        self.assertIn("Profile: SAST full with SSC", result.stdout)
        self.assertIn("Software Security Center", result.stdout)
        self.assertIn("ScanCentral SAST Sensor", result.stdout)
        self.assertIn("PostgreSQL", result.stdout)

    def test_known_issue_detector_matches_common_failure_patterns(self) -> None:
        result = self.run_wizard_functions(
            'printf "%s\n" "Back-off pulling image" "TRAEFIK DEFAULT CERT" "Insufficient memory" | known_issue_lines_from_text'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Image pull failure", result.stdout)
        self.assertIn("Traefik default certificate", result.stdout)
        self.assertIn("Insufficient memory", result.stdout)

    def test_full_lab_reset_clears_lab_acknowledgement_after_success(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp/lab"; ENV_FILE="$tmp/lab/.env"; ENV_EXAMPLE="$tmp/lab/.env.example"; '
            'ENV_BACKUP_DIR="$tmp/lab/.env.backups"; mkdir -p "$FORTIFY_HOME_K8S/certs"; printf "x" >"$ENV_FILE"; '
            'env_prepare_backup() { :; }; lab_destroy_deployments() { printf "DESTROYED:%s\n" "$1"; }; '
            'fortify_lab_show_action_warning() { :; }; wizard_log_event() { :; }; '
            'read -r _lab_ack; fortify_lab_record_acknowledgement; marker="$(fortify_lab_acknowledgement_file)"; '
            'printf "BEFORE=%s\n" "$([ -f "$marker" ] && echo yes || echo no)"; lab_reset_execute full; '
            'printf "AFTER=%s\n" "$([ -f "$marker" ] && echo yes || echo no)"',
            user_input="RESET FULL\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BEFORE=yes", result.stdout)
        self.assertIn("DESTROYED:all", result.stdout)
        self.assertIn("Lab-use acknowledgement reset", result.stdout)
        self.assertIn("AFTER=no", result.stdout)

    def test_complete_lab_reset_requires_typed_confirmation(self) -> None:
        result = self.run_wizard_functions(
            'fortify_lab_show_action_warning() { :; }; lab_shutdown_deployments() { printf BAD_RESET; }; wizard_log_event() { :; }; '
            'read -r _lab_ack; lab_reset_execute soft; printf "RC=%s\n" "$?"',
            user_input="nope\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Soft reset preview", result.stdout)
        self.assertIn("Reset cancelled", result.stdout)
        self.assertIn("RC=1", result.stdout)
        self.assertNotIn("BAD_RESET", result.stdout)

    def test_guided_setup_help_uses_help_center_topics(self) -> None:
        result = self.run_wizard_functions(
            'guided_setup_step_screen() { :; }; guided_setup_footer() { :; }; '
            'answers=(h q); ask() { local __target="$1"; shift || true; printf -v "$__target" "%s" "${answers[0]}"; answers=("${answers[@]:1}"); }; '
            'help_show_topic() { printf "HELP:%s\n" "$1"; }; '
            'guided_setup_menu; printf "RC=%s\n" "$?"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HELP:overview", result.stdout)
        self.assertIn("Guided Setup cancelled", result.stdout)
        self.assertIn("RC=130", result.stdout)

    def test_guided_setup_welcome_footer_only_shows_relevant_actions(self) -> None:
        result = self.run_wizard_functions('guided_setup_footer 0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  c. Continue", result.stdout)
        self.assertIn("  q. Cancel setup", result.stdout)
        for hidden in ("Edit values", "Skip", "Back", "Help"):
            self.assertNotIn(hidden, result.stdout)

    def test_guided_setup_steps_explain_purpose_impact_and_next_action(self) -> None:
        result = self.run_wizard_functions(
            'setup_profile_preview() { printf "  Profile preview\n"; }; '
            'setup_registry_status() { printf "  Registry status\n"; }; '
            'setup_tls_status() { printf "\nPurpose\n  TLS purpose\n\nCurrent configuration\n  TLS current\n\nImpact\n  TLS impact\n\nRecommended next action\n  TLS next\n"; }; '
            'setup_hosts_guidance() { printf "  host.example.test\n"; }; '
            'setup_readiness_items() { printf "  readiness item\n"; }; '
            'setup_review_pending() { printf "  pending item\n"; }; '
            'for step in 0 1 2 3 4 5 6 7 8 9; do guided_setup_step_screen "$step"; done'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("Purpose", "Impact", "Recommended next action"):
            self.assertGreaterEqual(result.stdout.count(expected), 10)
        self.assertIn("Orient the setup flow", result.stdout)
        self.assertIn("Define the lab identity", result.stdout)
        self.assertIn("Choose which Fortify Lab components", result.stdout)
        self.assertIn("Select the Fortify product-version bundle", result.stdout)
        self.assertIn("Prepare Docker Hub credentials", result.stdout)
        self.assertIn("Prepare fcli", result.stdout)

    def test_guided_setup_and_deployment_footers_render_vertical_options(self) -> None:
        result = self.run_wizard_functions('guided_setup_footer; guided_deployment_footer')
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("Options", "  e. Edit values", "  c. Continue", "  r. Retry operation", "  p. Pod logs", "  x. Export diagnostics bundle"):
            self.assertIn(expected, result.stdout)

    def test_domain_changes_are_only_exposed_through_domain_url_assistant(self) -> None:
        identity_keys = WIZARD.split("identity) printf", 1)[1].split(";;", 1)[0]
        self.assertIn("NAMESPACE", identity_keys)
        self.assertNotIn("DOMAIN", identity_keys)
        self.assertIn("2) domain_url_assistant", WIZARD)
        self.assertNotIn("env_guided_section_editor \"Lab identity and domain\" identity", WIZARD)

    def test_section_editor_exposes_numbered_controls_and_version_lookup(self) -> None:
        for expected in (
            "env_pending_set()",
            "p. Preview pending changes",
            "a. Apply pending changes",
            "d. Discard pending changes",
            "v. Validate / show guidance",
            "q. Quit safely",
            "deployment_versions_discover_into",
            "u. Check available versions",
            "flight_plan_versions_menu",
            "Select Fortify Flight Plan",
        ):
            self.assertIn(expected, WIZARD)

    def test_section_editor_discard_leaves_env_and_backups_untouched(self) -> None:
        result = self.run_wizard_functions(
            "tmp=$(mktemp -d); FORTIFY_HOME_K8S=\"$tmp\"; ENV_FILE=\"$tmp/.env\"; ENV_BACKUP_DIR=\"$tmp/.env.backups\"; "
            "printf \"%s\\n\" \"export NAMESPACE=\\\"oldns\\\"\" >\"$ENV_FILE\"; "
            "press_any() { :; }; read -r _lab_ack; "
            "env_guided_section_editor \"Kubernetes namespace\" identity; "
            "source \"$ENV_FILE\"; printf \"NAMESPACE=%s BACKUPS=%s\\n\" \"$NAMESPACE\" \"$(find \"$ENV_BACKUP_DIR\" -type f 2>/dev/null | wc -l)\"",
            user_input="1\nnewns\nd\nr\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NAMESPACE=oldns BACKUPS=0", result.stdout)

    def test_secret_pending_cart_redacts_values(self) -> None:
        result = self.run_wizard_functions(
            "tmp=$(mktemp -d); FORTIFY_HOME_K8S=\"$tmp\"; ENV_FILE=\"$tmp/.env\"; ENV_BACKUP_DIR=\"$tmp/.env.backups\"; "
            "printf \"%s\\n\" \"export DEFAULT_PASS=\\\"old-secret\\\"\" >\"$ENV_FILE\"; "
            "press_any() { :; }; read -r _lab_ack; "
            "env_guided_section_editor \"Credentials, users, and passwords\" credentials",
            user_input="1\nnew-secret\np\n\nr\ny\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DEFAULT_PASS", result.stdout)
        self.assertIn("<redacted> -> <redacted>", result.stdout)
        self.assertNotIn("new-secret", result.stdout)

    def test_deployment_versions_discovery_can_queue_latest_values(self) -> None:
        result = self.run_wizard_functions(
            "tmp=$(mktemp -d); FORTIFY_HOME_K8S=\"$tmp\"; ENV_FILE=\"$tmp/.env\"; ENV_BACKUP_DIR=\"$tmp/.env.backups\"; "
            "printf \"%s\\n\" \"export FORTIFY_SSC_CHART_VERSION=\\\"old\\\"\" >\"$ENV_FILE\"; "
            "env_section_keys() { [ \"$1\" = versions ] && printf \"%s\\n\" FORTIFY_SSC_CHART_VERSION || return 1; }; "
            "deployment_version_latest_for_key() { printf \"new-chart\\n\"; }; "
            "press_any() { :; }; read -r _lab_ack; "
            "env_guided_section_editor \"Deployment versions\" versions; "
            "source \"$ENV_FILE\"; printf \"VERSION=%s\\n\" \"$FORTIFY_SSC_CHART_VERSION\"",
            user_input="u\ny\na\ny\nn\n\nr\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("latest available: new-chart", result.stdout)
        self.assertIn("VERSION=new-chart", result.stdout)

    def test_deployment_versions_menu_exposes_flight_plan_upgrade_and_component_override(self) -> None:
        for expected in (
            "Full Flight Plan upgrade",
            "Advanced individual component override",
            "Show candidate Flight Plans",
            "flight_plan_full_upgrade_flow",
            "flight_plan_component_override_menu",
            "FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS",
            "Restore this component to current Flight Plan baseline",
        ):
            self.assertIn(expected, WIZARD)

    def test_full_flight_plan_upgrade_stages_through_pending_preview(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$PWD"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'cp .env.example "$ENV_FILE"; source "$ENV_FILE"; pending=(); '
            'confirm() { return 0; }; press_any() { :; }; '
            'flight_plan_full_upgrade_flow pending fortify-26.2; printf "COUNT=%s\n" "${#pending[@]}"; printf "%s\n" "${pending[@]}"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Current Flight Plan", result.stdout)
        self.assertIn("Target Flight Plan", result.stdout)
        self.assertIn("Upgrade safety", result.stdout)
        self.assertIn("FORTIFY_FLIGHT_PLAN=fortify-26.2", result.stdout)
        self.assertIn("COUNT=8", result.stdout)

    def test_component_override_marks_drift_and_restore_clears_marker(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$PWD"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'cp .env.example "$ENV_FILE"; source "$ENV_FILE"; pending=(); '
            'flight_plan_stage_component_from_plan pending sast fortify-26.2; flight_plan_stage_drift_marker pending sast; '
            'printf "STAGED:%s\n" "${pending[@]}"; '
            'flight_plan_clear_drift_marker pending sast; printf "RESTORE:%s\n" "${pending[@]}"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FORTIFY_SCSAST_CHART_VERSION=26.2.0-1", result.stdout)
        self.assertIn("FORTIFY_SCSAST_CTRL_IMAGE_TAG=26.2.0", result.stdout)
        self.assertIn("FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS=sast", result.stdout)
        self.assertIn("RESTORE:FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS=", result.stdout)

    def test_domain_assistant_updates_domain_and_derived_urls(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=\"old.test\"" "export SSC=\"ssc.$DOMAIN\"" "export SSC_URL=\"https://$SSC\"" >"$ENV_FILE"; '
            'updates=(); while IFS= read -r line; do updates+=("$line"); done < <(domain_url_updates lab.example.test); '
            'env_apply_updates domain-url "${updates[@]}" >/dev/null; '
            'source "$ENV_FILE"; printf "%s|%s|%s|%s\n" "$DOMAIN" "$SSC" "$LIM" "$SCSAST_CTRL_URL"; '
            'grep -E "export (DOMAIN|SSC|SSC_URL)=" "$ENV_FILE"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lab.example.test|ssc.lab.example.test|lim.lab.example.test|https://sast.lab.example.test/scancentral-ctrl/", result.stdout)
        self.assertIn('export SSC="ssc.$DOMAIN"', result.stdout)
        self.assertIn('export SSC_URL="https://$SSC"', result.stdout)

    def test_domain_assistant_normalizes_domains_to_lowercase_ingress_hosts(self) -> None:
        self.assertIn("domain=${domain,,}", WIZARD)
        self.assertIn("lowercase DNS-style domain", WIZARD)
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=\"old.test\"" "export SSC=\"ssc.$DOMAIN\"" "export SSC_URL=\"https://$SSC\"" >"$ENV_FILE"; '
            'ask() { local _v="$1"; shift; printf -v "$_v" "%s" "FortifyDemo.COM"; }; '
            'confirm() { return 0; }; press_any() { :; }; '
            'domain_url_assistant >/dev/null; source "$ENV_FILE"; printf "%s|%s|%s\n" "$DOMAIN" "$SSC" "$SSC_URL"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fortifydemo.com|ssc.fortifydemo.com|https://ssc.fortifydemo.com", result.stdout)

    def test_app_url_lookup_resolves_ssc_url_not_neighbor_variable(self) -> None:
        result = self.run_wizard_functions(
            'SSC_URL=https://ssc.example.test; LIM_URL=https://lim.example.test; '
            'printf "SSC=%s\nLIM=%s\n" "$(app_url_for_index 2)" "$(app_url_for_index 3)"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SSC=https://ssc.example.test", result.stdout)
        self.assertIn("LIM=https://lim.example.test", result.stdout)
        self.assertNotIn("SSC=LIM_URL", result.stdout)

    def test_app_url_display_marks_placeholder_url_values_invalid(self) -> None:
        result = self.run_wizard_functions(
            'SSC_URL=LIM_URL; printf "%s\n" "$(app_url_display_for_index 2)"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<invalid: SSC_URL=LIM_URL>", result.stdout)

    def test_config_validation_flags_placeholder_host_and_url_drift(self) -> None:
        result = self.run_wizard_functions(
            'python_config_available() { return 1; }; DOMAIN=fortifydemo.com; SSC=LIM; LIM=lim.fortifydemo.com; '
            'SCDAST=dast.fortifydemo.com; SCSAST=sast.fortifydemo.com; '
            'SSC_URL=LIM_URL; LIM_URL=https://lim.fortifydemo.com; '
            'SCDAST_URL=https://dast.fortifydemo.com; SCSAST_URL=https://sast.fortifydemo.com; '
            'SCSAST_CTRL_URL=https://sast.fortifydemo.com/scancentral-ctrl/; '
            'if deployment_config_guard; then printf BAD; else printf BLOCKED; fi'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BLOCKED", result.stdout)
        self.assertIn("SSC is set to placeholder-like value LIM", result.stdout)
        self.assertIn("SSC_URL is set to placeholder-like value LIM_URL", result.stdout)
        self.assertIn("Repair derived host and URL values from DOMAIN", result.stdout)

    def test_config_diagnostics_reports_raw_effective_expected_without_secrets(self) -> None:
        self.assertIn("config-diagnostics", WIZARD)
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; '
            'printf "%s\n" "export DOMAIN=\"fortifydemo.proxmox\"" "export SSC=\"LIM\"" "export SSC_URL=\"LIM_URL\"" "export DEFAULT_PASS=\"do-not-print\"" >"$ENV_FILE"; '
            'source "$ENV_FILE"; env_diagnostics'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("raw=LIM", result.stdout)
        self.assertIn("effective=LIM", result.stdout)
        self.assertEqual(result.stdout.count("SSC_URL is set to placeholder-like value LIM_URL"), 1)
        self.assertIn("expected=ssc.fortifydemo.proxmox", result.stdout)
        self.assertIn("SSC_URL is set to placeholder-like value LIM_URL", result.stdout)
        self.assertNotIn("do-not-print", result.stdout)

    def test_repair_domain_urls_rewrites_bad_derived_values_with_backup(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DOMAIN=\"fortifydemo.com\"" "export SSC=\"LIM\"" "export SSC_URL=\"LIM_URL\"" >"$ENV_FILE"; '
            'source "$ENV_FILE"; confirm() { return 0; }; env_repair_domain_urls >/dev/null; '
            'source "$ENV_FILE"; printf "%s|%s|%s|%s\n" "$SSC" "$SSC_URL" "$LIM" "$LIM_URL"; '
            'test -f "$FORTIFY_HOME_K8S/.env.rollback" && printf "ROLLBACK"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ssc.fortifydemo.com|https://ssc.fortifydemo.com|lim.fortifydemo.com|https://lim.fortifydemo.com", result.stdout)
        self.assertIn("ROLLBACK", result.stdout)

    def test_lab_hosts_resolution_warns_when_dns_points_at_proxy_endpoint(self) -> None:
        result = self.run_wizard_functions(
            'DOMAIN=example.test; lab_node_ip() { printf "10.0.0.5"; }; '
            'getent() { case "$2" in '
            'ssc.example.test) printf "10.0.0.9 STREAM\n" ;; '
            '*) printf "10.0.0.5 STREAM\n" ;; '
            'esac; }; '
            'lab_hosts_resolution_detail'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ssc.example.test=10.0.0.9", result.stdout)
        self.assertIn("TRAEFIK DEFAULT CERT", result.stdout)
        self.assertIn("404", result.stdout)


    def test_coredns_patch_refreshes_legacy_lab_hosts_block(self) -> None:
        helper = ROOT / "scripts/lib/coredns-lab-hosts.sh"
        corefile = ".:53 {\n    errors\n    hosts {\n        10.0.0.4 ssc.example.test sast.example.test\n        fallthrough\n    }\n    forward . 1.1.1.1\n}\n"
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; printf "%s" "$2" | fortify_patch_coredns_corefile 10.0.0.5 "ssc.lab.test sast.lab.test dast.lab.test lim.lab.test dashboard.lab.test"',
                "coredns-test",
                str(helper),
                corefile,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# fortifylab hosts begin", result.stdout)
        self.assertIn("10.0.0.5 ssc.lab.test sast.lab.test dast.lab.test lim.lab.test dashboard.lab.test", result.stdout)
        self.assertNotIn("10.0.0.4 ssc.example.test", result.stdout)
        self.assertEqual(result.stdout.count("hosts {"), 1)

    def test_coredns_patch_refreshes_managed_lab_hosts_block(self) -> None:
        helper = ROOT / "scripts/lib/coredns-lab-hosts.sh"
        corefile = ".:53 {\n    # fortifylab hosts begin\n    hosts {\n        10.0.0.4 ssc.old.test sast.old.test dast.old.test lim.old.test dashboard.old.test\n        fallthrough\n    }\n    # fortifylab hosts end\n    forward . 1.1.1.1\n}\n"
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; printf "%s" "$2" | fortify_patch_coredns_corefile 10.0.0.6 "ssc.new.test sast.new.test dast.new.test lim.new.test dashboard.new.test"',
                "coredns-test",
                str(helper),
                corefile,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("10.0.0.6 ssc.new.test sast.new.test dast.new.test lim.new.test dashboard.new.test", result.stdout)
        self.assertNotIn("old.test", result.stdout)
        self.assertEqual(result.stdout.count("# fortifylab hosts begin"), 1)

    def test_secret_values_are_redacted_in_preview(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'printf "%s\n" "export DEFAULT_PASS=\"old-secret\"" >"$ENV_FILE"; '
            'env_preview_changes "DEFAULT_PASS=new-secret"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DEFAULT_PASS", result.stdout)
        self.assertIn("<redacted> -> <redacted>", result.stdout)
        self.assertNotIn("old-secret", result.stdout)
        self.assertNotIn("new-secret", result.stdout)

    def test_mkcert_root_ca_export_copies_public_ca_only(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'mkdir -p "$tmp/bin" "$tmp/caroot"; printf PUBLIC >"$tmp/caroot/rootCA.pem"; printf PRIVATE >"$tmp/caroot/rootCA-key.pem"; '
            'printf "%s\n" "#!/bin/sh" "echo \"$tmp/caroot\"" >"$tmp/bin/mkcert"; chmod +x "$tmp/bin/mkcert"; PATH="$tmp/bin:$PATH"; '
            'mkcert_root_ca_export; printf "DEST="; cat "$tmp/certs/rootCA.pem"; printf "\nFILES="; ls "$tmp/certs"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DEST=PUBLIC", result.stdout)
        self.assertIn("rootCA.pem", result.stdout)
        self.assertNotIn("rootCA-key.pem", result.stdout)
        self.assertNotIn("private rootCA", result.stdout)
        self.assertNotIn("PRIVATE", result.stdout)

    def test_mkcert_trust_guidance_warns_not_to_share_private_key(self) -> None:
        result = self.run_wizard_functions('mkcert_trust_instructions')
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("Windows", "macOS", "Ubuntu/Debian", "Firefox/NSS", "Never import, copy, or share the mkcert private CA key"):
            self.assertIn(expected, result.stdout)


    def test_guided_deployment_profiles_expand_dependencies(self) -> None:
        cases = {
            "ssc_only": ["prereqs", "inputs", "preflight", "certs", "dashboard", "secrets", "mysql", "ssc", "configure"],
            "sast_standalone": ["prereqs", "inputs", "preflight", "certs", "dashboard", "secrets", "sast_controller"],
            "sast_full": ["prereqs", "inputs", "preflight", "certs", "dashboard", "secrets", "mysql", "ssc", "sast_controller", "sast_sensor", "configure"],
            "dast_full": ["prereqs", "inputs", "preflight", "certs", "dashboard", "secrets", "mysql", "postgresql", "ssc", "lim", "dast_core", "dast_scanner", "configure"],
            "sample_apps": ["prereqs", "inputs", "preflight", "certs", "dashboard", "secrets", "sample_juice_shop", "sample_webgoat", "sample_dvwa"],
        }
        for profile, expected in cases.items():
            with self.subTest(profile=profile):
                result = self.run_wizard_functions(
                    f'guided_apply_deployment_profile {profile}; printf "%s\n" "${{GUIDED_STEP_ID[*]}}"'
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip().splitlines()[-1].split(), expected)

    def test_guided_custom_profile_adds_sensor_dependencies(self) -> None:
        result = self.run_wizard_functions(
            'GUIDED_DEPLOYMENT_COMPONENTS="sast_sensor dast_scanner"; '
            'guided_apply_deployment_profile custom; '
            'printf "COMPONENTS=%s\nSTEPS=%s\n" "$GUIDED_DEPLOYMENT_COMPONENTS" "${GUIDED_STEP_ID[*]}"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sast_sensor", result.stdout)
        self.assertIn("sast_controller", result.stdout)
        self.assertIn("dast_core", result.stdout)
        self.assertIn("postgresql", result.stdout)

    def test_guided_profile_selection_can_continue_without_saving(self) -> None:
        result = self.run_wizard_functions(
            'read _ack; confirm() { return 1; }; env_apply_updates() { printf BAD_SAVE; }; guided_profile_menu; '
            'printf "PROFILE=%s STEPS=%s\n" "$GUIDED_DEPLOYMENT_PROFILE" "${GUIDED_STEP_ID[*]}"',
            "2\nn\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using this profile for the current wizard session only", result.stdout)
        self.assertIn("PROFILE=sast_standalone", result.stdout)
        self.assertIn("sast_controller", result.stdout)
        self.assertNotIn("BAD_SAVE", result.stdout)

    def test_guided_profile_menu_labels_sample_apps_and_custom_separately(self) -> None:
        self.assertIn("printf '  6. Sample applications only\\n'", WIZARD)
        self.assertIn("printf '  7. Custom\\n\\n'", WIZARD)
        self.assertIn("6) fortify_lab_show_action_warning vulnerable-sample; profile=sample_apps ;;", WIZARD)
        self.assertIn("7) guided_custom_component_prompt; return $? ;;", WIZARD)

    def test_sast_sensor_live_state_does_not_complete_from_controller_only(self) -> None:
        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; cluster_reachable() { return 0; }; '
            'kube() { case "$*" in '
            '*"get pods"*) printf "scancentral-sast-controller-0 1/1 Running 0 1m\n" ;; '
            '*"scancentral-sast-controller"*"jsonpath={.spec.replicas}"*) printf 1 ;; '
            '*"scancentral-sast-controller"*"jsonpath={.status.readyReplicas}"*) printf 1 ;; '
            '*) return 1 ;; esac; }; '
            'printf "STATE=%s\n" "$(guided_step_live_state sast_sensor)"; '
            'if sast_sensor_ready; then printf READY; else printf NOT_READY; fi'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STATE=pending", result.stdout)
        self.assertIn("NOT_READY", result.stdout)
        self.assertNotIn("STATE=complete", result.stdout)

    def test_sast_sensor_live_state_completes_with_sensor_workload(self) -> None:
        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; cluster_reachable() { return 0; }; '
            'kube() { case "$*" in '
            '*"get pods"*) printf "scancentral-sast-controller-0 1/1 Running 0 1m\nscancentral-sast-sensor-linux-0 1/1 Running 0 1m\n" ;; '
            '*"scancentral-sast-controller"*"jsonpath={.spec.replicas}"*) printf 1 ;; '
            '*"scancentral-sast-controller"*"jsonpath={.status.readyReplicas}"*) printf 1 ;; '
            '*"scancentral-sast-sensor-linux"*"jsonpath={.spec.replicas}"*) printf 1 ;; '
            '*"scancentral-sast-sensor-linux"*"jsonpath={.status.readyReplicas}"*) printf 1 ;; '
            '*) return 1 ;; esac; }; '
            'printf "STATE=%s\n" "$(guided_step_live_state sast_sensor)"; '
            'if sast_sensor_ready; then printf READY; else printf NOT_READY; fi'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STATE=complete", result.stdout)
        self.assertIn("READY", result.stdout)

    def test_optional_skip_is_explicit_and_required_skip_is_rejected(self) -> None:
        self.assertIn("GUIDED_ALL_STEP_OPTIONAL=(1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1)", WIZARD)
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
            "guided_component_endpoint_detail()", 1
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
        self.assertIn("GUIDED_ALL_STEP_TIMEOUT=(900 300 120 180 300 60", WIZARD)
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


    def test_auto_advance_countdown_uses_numbered_ephemeral_status(self) -> None:
        self.assertIn('GUIDED_AUTO_ADVANCE_DELAY="${GUIDED_AUTO_ADVANCE_DELAY:-5}"', WIZARD)
        countdown = WIZARD.split("guided_countdown()", 1)[1].split("guided_step_enabled()", 1)[0]
        self.assertIn('GUIDED_AUTO_ADVANCE_DELAY:-5', countdown)
        self.assertIn('read -rsn1 -t 1 control', countdown)
        self.assertIn("[%d/%d]", countdown)
        self.assertIn("Press i to stay here", countdown)
        self.assertIn("Auto-advance paused: staying interactive", countdown)
        self.assertIn("\\r\\033[K", countdown)
        self.assertNotIn("Press i for interactive control", countdown)

    def test_prerequisite_menu_shows_completion_indicators(self) -> None:
        self.assertIn("prereqs_status_table()", WIZARD)
        self.assertIn('"Host prerequisites: $ready/4 ready."', WIZARD)
        self.assertIn("All prerequisite indicators are complete", WIZARD)
        self.assertIn("Next missing: group access in this shell", WIZARD)
        self.assertIn("Refresh group access (microk8s/docker) now", WIZARD)

    def test_prerequisite_probe_requires_microk8s_access(self) -> None:
        self.assertIn("microk8s_access_ready()", WIZARD)
        self.assertIn("id -nG | grep -qw microk8s", WIZARD)
        self.assertIn("microk8s status --wait-ready", WIZARD)
        self.assertIn("java_ready && docker_ready && mkcert_ready && microk8s_access_ready", WIZARD)

    def test_group_activation_is_automatic_not_menu_gated(self) -> None:
        # install_docker and install_microk8s both auto-activate group access
        # instead of just telling the user to press a key.
        self.assertIn('sudo usermod -aG docker "$target_user"', WIZARD)
        install_docker = WIZARD.split("install_docker()", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("ensure_active_groups", install_docker)
        install_microk8s = WIZARD.split("install_microk8s() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("ensure_active_groups", install_microk8s)
        # The wizard also self-heals a stale shell on every launch, not just
        # right after an install.
        self.assertIn("fortify_lab_require_acknowledgement || exit 1\n    ensure_active_groups", WIZARD)

    def test_ensure_active_groups_reexec_guard_and_fallback(self) -> None:
        self.assertIn("FORTIFY_GROUP_REEXEC", WIZARD)
        self.assertIn("Could not find sg to refresh group access automatically", WIZARD)

    def test_fortify_groups_pending_activation_detects_gap(self) -> None:
        result = self.run_wizard_functions(
            "getent() { "
            '  case "$2" in '
            '    microk8s) printf "microk8s:x:999:%s\\n" "$(id -un)" ;; '
            '    docker) printf "docker:x:998:%s\\n" "$(id -un)" ;; '
            "  esac "
            "}; "
            "docker() { :; }; microk8s() { :; }; "
            'printf "pending=[%s]\\n" "$(fortify_groups_pending_activation | tr \'\\n\' \',\')"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pending=[microk8s,docker,]", result.stdout)

    def test_fortify_groups_pending_activation_empty_when_already_active(self) -> None:
        result = self.run_wizard_functions(
            "getent() { "
            '  case "$2" in '
            '    microk8s) printf "microk8s:x:999:%s\\n" "$(id -un)" ;; '
            '    docker) printf "docker:x:998:%s\\n" "$(id -un)" ;; '
            "  esac "
            "}; "
            'id() { if [ "$1" = "-un" ]; then command id -un; else printf "%s wheel microk8s docker\\n" "$(id -un)"; fi; }; '
            "docker() { :; }; microk8s() { :; }; "
            'printf "pending=[%s]\\n" "$(fortify_groups_pending_activation | tr \'\\n\' \',\')"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pending=[]", result.stdout)

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
        self.assertIn("Congratulations, FortifyLab is ready", result.stdout)
        self.assertIn("[1/2] One already complete; continuing to [2/2] Two.", result.stdout)


    def test_wait_screen_redraws_without_full_clear_flash(self) -> None:
        self.assertIn("guided_wait_screen_enter()", WIZARD)
        self.assertIn("guided_wait_screen_render_start()", WIZARD)
        self.assertIn("guided_wait_screen_render_finish()", WIZARD)
        self.assertIn("guided_wait_screen_leave()", WIZARD)
        self.assertIn("guided_wait_screen_tty()", WIZARD)
        self.assertIn("FORTIFY_GUIDED_WAIT_ALT_SCREEN", WIZARD)
        self.assertIn("terminal alternate screen", WIZARD)
        self.assertIn(r"printf '\033[?1049h\033[?25l\033[H\033[J'", WIZARD)
        self.assertIn(r"printf '\033[H\033[J'", WIZARD)
        self.assertIn(r"printf '\033[?25h\033[?1049l'", WIZARD)
        self.assertIn(r"printf '\033[K%s\n'", WIZARD)
        self.assertNotIn("trap guided_wait_screen_leave RETURN", WIZARD)

        wait_body = WIZARD.split("guided_wait_for_step()", 1)[1].split("wizard_deployment_plan()", 1)[0]
        self.assertNotIn("clear", wait_body)
        self.assertIn('guided_wait_screen_render "$id" "$label"', wait_body)
        self.assertIn("guided_wait_screen_leave", wait_body)

    def test_resume_labels_in_progress_work(self) -> None:
        self.assertIn("in progress", WIZARD)
        self.assertIn("guided_step_in_progress()", WIZARD)
        self.assertIn("Watch verification", WIZARD)
        self.assertIn("Probe:", WIZARD)
        self.assertIn("probe $probe is still failing", WIZARD)

    def test_numbered_kubernetes_resource_selector_filters_resources(self) -> None:
        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; '
            'kube() { case "$*" in '
            '"-n fortify get pod -o name") printf "pod/mysql-0\npod/ssc-webapp-0\npod/ssc-worker-0\n" ;; '
            'esac; }; '
            'k8s_select_resource pod "Pick pod" ssc; '
            'printf "SELECTED=%s/%s\n" "$K8S_SELECTED_RESOURCE_KIND" "$K8S_SELECTED_RESOURCE_NAME"',
            "2\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Filter: ssc", result.stdout)
        self.assertIn("1. ssc-webapp-0", result.stdout)
        self.assertIn("2. ssc-worker-0", result.stdout)
        self.assertIn("SELECTED=pod/ssc-worker-0", result.stdout)

    def test_numbered_kubernetes_resource_selector_handles_empty_lists(self) -> None:
        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; '
            'kube() { case "$*" in '
            '"-n fortify get pod -o name") printf "pod/mysql-0\n" ;; '
            'esac; }; '
            'if k8s_select_resource pod "Pick pod" ssc; then printf BAD; else printf EMPTY_BACK; fi',
            "b\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No pods matched 'ssc'", result.stdout)
        self.assertIn("EMPTY_BACK", result.stdout)

    def test_logs_menus_reuse_numbered_selector_and_pod_log_actions(self) -> None:
        self.assertIn("k8s_select_resource()", WIZARD)
        self.assertIn("k8s_resource_names()", WIZARD)
        self.assertIn("pod_log_action_menu()", WIZARD)
        self.assertIn('k8s_select_resource pod "Select a pod"', WIZARD)
        self.assertIn('k8s_select_resource pod "Select a pod" "" "$prefix"', WIZARD)
        self.assertIn("--all-containers --tail=200", WIZARD)
        self.assertIn('follow_pod_logs_safe "$pod" 100 || true', WIZARD)
        self.assertIn("--all-containers --previous --tail=200", WIZARD)

        result = self.run_wizard_functions(
            'cluster_reachable() { return 0; }; '
            'k8s_resource_names() { printf "ssc-webapp-0\nssc-webapp-1\n"; }; '
            'k8s_select_resource() { printf "SELECTOR:%s|%s|%s|%s\n" "$1" "$2" "$3" "$4"; K8S_SELECTED_RESOURCE_NAME=ssc-webapp-1; return 0; }; '
            'pod_log_action_menu() { printf "LOGS:%s\n" "$1"; }; '
            'logs_for_prefix ssc-webapp'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SELECTOR:pod|Select a pod||ssc-webapp", result.stdout)
        self.assertIn("LOGS:ssc-webapp-1", result.stdout)

    def test_scoped_logs_skip_selector_when_only_one_pod_matches(self) -> None:
        result = self.run_wizard_functions(
            'cluster_reachable() { return 0; }; '
            'k8s_resource_names() { printf "ssc-webapp-0\n"; }; '
            'k8s_select_resource() { printf BAD_SELECTOR; return 1; }; '
            'pod_log_action_menu() { printf "LOGS:%s\n" "$1"; }; '
            'logs_for_prefix ssc-webapp'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOGS:ssc-webapp-0", result.stdout)
        self.assertNotIn("BAD_SELECTOR", result.stdout)

    def test_follow_logs_uses_interrupt_safe_helper(self) -> None:
        self.assertIn("follow_pod_logs_safe()", WIZARD)
        self.assertIn("restore_int_trap()", WIZARD)
        self.assertIn('follow_pod_logs_safe "$pod" 100 || true', WIZARD)
        self.assertNotIn('logs --all-containers --follow --tail=100 "$pod" || true', WIZARD)

    def test_stream_logs_restores_trap_and_avoids_process_group_kill(self) -> None:
        self.assertIn('saved_int_trap=$(trap -p INT || true)', WIZARD)
        self.assertIn('restore_int_trap "$saved_int_trap"', WIZARD)
        self.assertIn('pkill -TERM -P "$p"', WIZARD)
        self.assertNotIn("trap 'kill 0' EXIT", WIZARD)
        self.assertNotIn("return 0' INT", WIZARD)

    def test_follow_logs_interrupted_child_returns_to_shell_and_restores_outer_trap(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); '
            'printf "%s\n" "#!/usr/bin/env bash" "printf \'FAKE_KUBE:%s\\n\' \"\\$*\"" "exit 130" >"$tmp/kube"; '
            'chmod +x "$tmp/kube"; '
            'KUBECTL="$tmp/kube"; NAMESPACE=fortify; '
            'note() { printf "NOTE:%s\n" "$*"; }; '
            'trap \'printf "OUTER_INT\\n"\' INT; '
            'follow_pod_logs_safe ssc-webapp-0 7; '
            'trap -p INT; printf "AFTER_FOLLOW\n"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (
            "FAKE_KUBE:-n",
            "FAKE_KUBE:fortify",
            "FAKE_KUBE:logs",
            "FAKE_KUBE:--follow",
            "FAKE_KUBE:--tail=7",
            "FAKE_KUBE:--ignore-errors=true",
            "FAKE_KUBE:ssc-webapp-0",
        ):
            self.assertIn(expected, result.stdout)
        self.assertIn("Stopped following logs for ssc-webapp-0", result.stdout)
        self.assertIn("OUTER_INT", result.stdout)
        self.assertIn("AFTER_FOLLOW", result.stdout)

    def test_guided_wait_logs_skip_selector_when_only_one_pod_matches(self) -> None:
        result = self.run_wizard_functions(
            'cluster_reachable() { return 0; }; '
            'guided_step_pod_prefixes() { printf "ssc-webapp"; }; '
            'k8s_resource_names() { printf "ssc-webapp-0\n"; }; '
            'k8s_select_resource() { printf BAD_SELECTOR; return 1; }; '
            'pod_log_action_menu() { printf "LOGS:%s\n" "$1"; }; '
            'guided_step_pod_logs ssc SSC'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOGS:ssc-webapp-0", result.stdout)
        self.assertNotIn("BAD_SELECTOR", result.stdout)

    def test_wait_screen_exposes_contextual_pod_logs_without_losing_wizard_log(self) -> None:
        self.assertIn("guided_step_pod_logs()", WIZARD)
        self.assertIn("p. Pod logs", WIZARD)
        self.assertIn("l. Wizard log", WIZARD)
        self.assertIn('[Pp])', WIZARD)
        self.assertIn('guided_step_pod_logs "$id" "$label"', WIZARD)
        self.assertIn("control=pod_logs", WIZARD)
        self.assertIn("control=view_log", WIZARD)

        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; '
            'cluster_reachable() { return 0; }; '
            'kube() { case "$*" in '
            '"-n fortify get pod -o name") return 0 ;; '
            '"-n fortify get events --sort-by=.lastTimestamp") printf "LAST EVENT\n" ;; '
            'esac; }; '
            'press_any() { :; }; '
            'guided_step_pod_logs mysql MySQL || true'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No pods matching 'mysql' have appeared yet", result.stdout)
        self.assertIn("Recent events", result.stdout)

    def test_guided_screens_split_live_diagnostics_from_bundle_export(self) -> None:
        self.assertIn("guided_live_diagnostics()", WIZARD)
        self.assertIn("guided_diagnostics_bundle()", WIZARD)
        self.assertIn("d. Live diagnostics", WIZARD)
        self.assertIn("x. Export diagnostics bundle", WIZARD)
        self.assertIn("control=live_diagnostics", WIZARD)
        self.assertIn("control=diagnostics_bundle", WIZARD)
        self.assertIn("r. Retry operation", WIZARD)
        self.assertIn('GUIDED_WAIT_LAST_STATE="retry"', WIZARD)

    def test_guided_step_menu_can_open_contextual_pod_logs(self) -> None:
        self.assertIn('guided_step_has_pod_logs "$id" && echo "  p. Pod logs"', WIZARD)
        self.assertIn('guided_step_pod_logs "$id" "${GUIDED_STEP_LABEL[$idx]}"', WIZARD)
        self.assertIn('guided_live_diagnostics "$id" "${GUIDED_STEP_LABEL[$idx]}"', WIZARD)

    def test_guided_live_diagnostics_prints_step_scoped_sections(self) -> None:
        result = self.run_wizard_functions(
            'NAMESPACE=fortify; KUBECTL=kube; SSC=ssc.example.test; '
            'cluster_reachable() { return 0; }; '
            'guided_step_live_status() { printf pending; }; '
            'guided_step_why_pending() { printf "waiting for endpoint"; }; '
            'guided_print_pods() { printf "  ssc-webapp-0 0/1 Running\n"; }; '
            'kube() { case "$*" in '
            '"-n fortify get service ssc-service") return 0 ;; '
            '"-n fortify get service ssc-service -o custom-columns=NAME:.metadata.name,TYPE:.spec.type,PORTS:.spec.ports[*].port") printf "NAME TYPE PORTS\nssc-service ClusterIP 443\n" ;; '
            '"-n fortify get endpoints ssc-service") return 0 ;; '
            '"-n fortify get endpoints ssc-service -o custom-columns=NAME:.metadata.name,ENDPOINTS:.subsets[*].addresses[*].ip,PORTS:.subsets[*].ports[*].port") printf "NAME ENDPOINTS PORTS\nssc-service 10.1.1.2 8443\n" ;; '
            '"-n fortify get ingress -o custom-columns=NAME:.metadata.name,CLASS:.spec.ingressClassName,HOSTS:.spec.rules[*].host,ADDRESS:.status.loadBalancer.ingress[*].ip") printf "NAME CLASS HOSTS ADDRESS\nssc-ingress public ssc.example.test <none>\n" ;; '
            '"-n fortify get events --sort-by=.lastTimestamp") printf "LAST SEEN TYPE REASON OBJECT MESSAGE\n1m Warning Failed pod/ssc-webapp-0 demo\n" ;; '
            '*) return 1 ;; esac; }; '
            'guided_live_diagnostics ssc SSC'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Live diagnostics for SSC", result.stdout)
        self.assertIn("waiting for endpoint", result.stdout)
        self.assertIn("ssc-webapp-0", result.stdout)
        self.assertIn("ssc-service", result.stdout)
        self.assertIn("ssc-ingress", result.stdout)


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

    def test_lab_lifecycle_controls_use_existing_component_scripts(self) -> None:
        self.assertIn("lab_lifecycle_menu()", WIZARD)
        self.assertIn("APP_GUIDED_STEP=", WIZARD)
        self.assertIn("lab_lifecycle_app_index_selected()", WIZARD)
        self.assertIn("lab_lifecycle_selected_step_indexes()", WIZARD)
        self.assertIn("Start selected profile workloads", WIZARD)
        self.assertIn("Start all lab deployments", WIZARD)
        self.assertIn("DESTROY SELECTED PROFILE", WIZARD)
        self.assertIn("DESTROY FORTIFY LAB", WIZARD)
        self.assertIn("action=lab_lifecycle_start operation=shutdown scope=selected", WIZARD)
        self.assertIn("action=lab_lifecycle_start operation=destroy scope=$scope", WIZARD)

    def test_lab_shutdown_stops_workloads_in_reverse_dependency_order(self) -> None:
        result = self.run_wizard_functions(
            'run_app_scripts() { printf "RUN:%s\n" "$1"; }; '
            'wizard_log_event() { :; }; '
            'lab_shutdown_deployments'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        runs = [line.removeprefix("RUN:") for line in result.stdout.splitlines() if line.startswith("RUN:")]
        self.assertEqual(
            runs,
            [
                "apps/scdast/scanner/stop.sh",
                "apps/scdast/core/stop.sh",
                "apps/scsast/stop.sh",
                "apps/lim/stop.sh",
                "apps/ssc/stop.sh",
                "apps/postgresql/stop.sh",
                "apps/mysql/stop.sh",
            ],
        )
        self.assertIn("Persistent data is preserved", result.stdout)

    def test_lab_start_runs_forward_and_verifies_each_component(self) -> None:
        result = self.run_wizard_functions(
            'guided_run_and_verify() { printf "VERIFY:%s:%s:%s\n" "$1" "$2" "$GUIDED_MODE_CONTEXT"; }; '
            'wizard_log_event() { :; }; '
            'GUIDED_MODE_CONTEXT=resume; lab_start_deployments; printf "MODE=%s\n" "$GUIDED_MODE_CONTEXT"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        verifies = [line for line in result.stdout.splitlines() if line.startswith("VERIFY:")]
        self.assertEqual(
            verifies,
            [
                "VERIFY:mysql:MySQL:lifecycle",
                "VERIFY:postgresql:PostgreSQL:lifecycle",
                "VERIFY:ssc:Software Security Center:lifecycle",
                "VERIFY:lim:LIM:lifecycle",
                "VERIFY:sast_controller:ScanCentral SAST Controller:lifecycle",
                "VERIFY:sast_sensor:ScanCentral SAST Sensor:lifecycle",
                "VERIFY:dast_core:ScanCentral DAST Core:lifecycle",
                "VERIFY:dast_scanner:ScanCentral DAST Scanner:lifecycle",
            ],
        )
        self.assertIn("MODE=resume", result.stdout)

    def test_full_lab_destroy_requires_typed_confirmation_and_uses_reverse_order(self) -> None:
        cancelled = self.run_wizard_functions(
            'fortify_lab_show_action_warning() { :; }; '
            'run_app_scripts() { printf "RUN:%s\n" "$1"; }; '
            'wizard_log_event() { :; }; '
            'read _lab_ack; lab_destroy_deployments all; printf "RC=%s\n" "$?"',
            "not today\n",
        )
        self.assertEqual(cancelled.returncode, 0, cancelled.stderr)
        self.assertIn("Teardown cancelled", cancelled.stdout)
        self.assertNotIn("RUN:", cancelled.stdout)
        self.assertIn("RC=1", cancelled.stdout)

        confirmed = self.run_wizard_functions(
            'fortify_lab_show_action_warning() { :; }; '
            'run_app_scripts() { printf "RUN:%s\n" "$1"; }; '
            'wizard_log_event() { :; }; '
            'read _lab_ack; lab_destroy_deployments all',
            "DESTROY FORTIFY LAB\n",
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        runs = [line.removeprefix("RUN:") for line in confirmed.stdout.splitlines() if line.startswith("RUN:")]
        self.assertEqual(
            runs,
            [
                "apps/scdast/core/destroy.sh apps/scdast/scanner/destroy.sh",
                "apps/scsast/destroy.sh",
                "apps/lim/destroy.sh",
                "apps/ssc/destroy.sh",
                "apps/postgresql/destroy.sh",
                "apps/mysql/destroy.sh",
            ],
        )
        self.assertIn("Full lab teardown preview", confirmed.stdout)

    def test_lifecycle_start_uses_selected_profile_steps(self) -> None:
        result = self.run_wizard_functions(
            'FORTIFY_DEPLOYMENT_PROFILE=sast_full; guided_apply_deployment_profile sast_full; '
            'guided_run_and_verify() { printf "VERIFY:%s:%s\n" "$1" "$2"; }; '
            'wizard_log_event() { :; }; '
            'lab_start_deployments selected'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        verifies = [line for line in result.stdout.splitlines() if line.startswith("VERIFY:")]
        self.assertEqual(
            verifies,
            [
                "VERIFY:mysql:MySQL",
                "VERIFY:ssc:Software Security Center",
                "VERIFY:sast_controller:ScanCentral SAST Controller",
                "VERIFY:sast_sensor:ScanCentral SAST Sensor",
            ],
        )
        self.assertNotIn("VERIFY:postgresql", result.stdout)
        self.assertNotIn("VERIFY:lim", result.stdout)
        self.assertNotIn("VERIFY:dast", result.stdout)

    def test_express_deployment_uses_selected_profile_steps(self) -> None:
        result = self.run_wizard_functions(
            'FORTIFY_DEPLOYMENT_PROFILE=sast_full; '
            'fresh_deployment_guard() { return 0; }; wizard_deployment_plan() { :; }; '
            'confirm() { return 0; }; press_any() { :; }; '
            'guided_run_and_verify() { printf "VERIFY:%s:%s\n" "$1" "$2"; }; '
            'deploy_from_scratch'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        verifies = [line for line in result.stdout.splitlines() if line.startswith("VERIFY:")]
        self.assertEqual(
            verifies,
            [
                "VERIFY:preflight:Deployment pre-flight",
                "VERIFY:certs:TLS certificates",
                "VERIFY:dashboard:Kubernetes Dashboard",
                "VERIFY:secrets:Kubernetes Secrets",
                "VERIFY:mysql:MySQL",
                "VERIFY:ssc:Software Security Center",
                "VERIFY:sast_controller:ScanCentral SAST Controller",
                "VERIFY:sast_sensor:ScanCentral SAST Sensor",
            ],
        )
        self.assertNotIn("VERIFY:postgresql", result.stdout)
        self.assertNotIn("VERIFY:lim", result.stdout)
        self.assertNotIn("VERIFY:dast", result.stdout)
        self.assertNotIn("VERIFY:configure", result.stdout)

    def test_express_deployment_ssc_only_skips_sast_and_dast_steps(self) -> None:
        result = self.run_wizard_functions(
            'FORTIFY_DEPLOYMENT_PROFILE=ssc_only; '
            'fresh_deployment_guard() { return 0; }; wizard_deployment_plan() { :; }; '
            'confirm() { return 0; }; press_any() { :; }; '
            'guided_run_and_verify() { printf "VERIFY:%s:%s\n" "$1" "$2"; }; '
            'deploy_from_scratch'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        verifies = [line for line in result.stdout.splitlines() if line.startswith("VERIFY:")]
        self.assertEqual(
            verifies,
            [
                "VERIFY:preflight:Deployment pre-flight",
                "VERIFY:certs:TLS certificates",
                "VERIFY:dashboard:Kubernetes Dashboard",
                "VERIFY:secrets:Kubernetes Secrets",
                "VERIFY:mysql:MySQL",
                "VERIFY:ssc:Software Security Center",
            ],
        )
        self.assertNotIn("VERIFY:sast", result.stdout)
        self.assertNotIn("VERIFY:dast", result.stdout)
        self.assertNotIn("VERIFY:lim", result.stdout)

    def test_lifecycle_shutdown_uses_selected_profile_scripts(self) -> None:
        result = self.run_wizard_functions(
            'FORTIFY_DEPLOYMENT_PROFILE=sast_full; guided_apply_deployment_profile sast_full; '
            'run_app_scripts() { printf "RUN:%s\n" "$1"; }; '
            'wizard_log_event() { :; }; '
            'lab_shutdown_deployments selected'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        runs = [line.removeprefix("RUN:") for line in result.stdout.splitlines() if line.startswith("RUN:")]
        self.assertEqual(
            runs,
            [
                "apps/scsast/stop.sh",
                "apps/ssc/stop.sh",
                "apps/mysql/stop.sh",
            ],
        )
        self.assertNotIn("apps/postgresql/stop.sh", result.stdout)
        self.assertNotIn("apps/lim/stop.sh", result.stdout)
        self.assertNotIn("apps/scdast", result.stdout)

    def test_cluster_status_is_profile_aware_for_limited_deployments(self) -> None:
        result = self.run_wizard_functions(
            'FORTIFY_DEPLOYMENT_PROFILE=sast_full; guided_apply_deployment_profile sast_full; '
            'NAMESPACE=fortify; KUBECTL=kube; cluster_reachable() { return 0; }; '
            'kube() { printf "%s\n" '
            '"mysql-0 1/1 Running 0 1m" '
            '"ssc-webapp-0 1/1 Running 0 1m" '
            '"scancentral-sast-controller-0 1/1 Running 0 1m" '
            '"postgresql-0 0/1 Running 0 1m" '
            '"lim-0 0/1 Running 0 1m" '
            '"sdast-core-0 0/1 Pending 0 1m"; }; '
            'status_cluster'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cluster: selected profile pods ready (3/3 running)", result.stdout)
        self.assertNotIn("3/6", result.stdout)


    def test_destroy_scripts_treat_missing_helm_releases_as_already_absent(self) -> None:
        helper = (ROOT / "scripts/lib/k8s-destroy.sh").read_text(encoding="utf-8")
        self.assertIn("fortify_helm_delete_if_exists()", helper)
        self.assertIn('status "$release"', helper)
        self.assertIn('already absent; skipping Helm delete', helper)

        for script in (
            "apps/mysql/destroy.sh",
            "apps/postgresql/destroy.sh",
            "apps/ssc/destroy.sh",
            "apps/lim/destroy.sh",
            "apps/scsast/destroy.sh",
            "apps/scdast/core/destroy.sh",
            "apps/scdast/scanner/destroy.sh",
        ):
            with self.subTest(script=script):
                body = (ROOT / script).read_text(encoding="utf-8")
                self.assertIn("scripts/lib/k8s-destroy.sh", body)
                self.assertIn("fortify_helm_delete_if_exists", body)


    def test_mysql_destroy_removes_chart_created_data_claim(self) -> None:
        body = (ROOT / "apps/mysql/destroy.sh").read_text(encoding="utf-8")
        self.assertIn('delete pvc data-mysql-0 --ignore-not-found', body)


    def test_stop_scripts_treat_missing_statefulsets_as_already_stopped(self) -> None:
        helper = (ROOT / "scripts/lib/k8s-scale.sh").read_text(encoding="utf-8")
        self.assertIn("fortify_scale_statefulset_if_exists()", helper)
        self.assertIn('get statefulset "$statefulset"', helper)
        self.assertIn("already stopped", helper)

        expected_statefulsets = {
            "apps/mysql/stop.sh": ["mysql"],
            "apps/postgresql/stop.sh": ["postgresql"],
            "apps/ssc/stop.sh": ["ssc-webapp"],
            "apps/lim/stop.sh": ["lim"],
            "apps/scsast/stop.sh": ["scancentral-sast-controller", "scancentral-sast-worker-linux"],
            "apps/scdast/core/stop.sh": [
                "sdast-core-scancentral-dast-core-api",
                "sdast-core-scancentral-dast-core-globalservice",
                "sdast-core-scancentral-dast-core-utilityservice",
            ],
            "apps/scdast/scanner/stop.sh": ["sdast-scanner-scancentral-dast-scanner"],
        }
        for script, statefulsets in expected_statefulsets.items():
            with self.subTest(script=script):
                body = (ROOT / script).read_text(encoding="utf-8")
                self.assertIn("scripts/lib/k8s-scale.sh", body)
                self.assertIn("fortify_scale_statefulset_if_exists", body)
                for statefulset in statefulsets:
                    self.assertIn(statefulset, body)

    def test_scale_helper_treats_missing_statefulset_as_success(self) -> None:
        helper = ROOT / "scripts/lib/k8s-scale.sh"
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; '
                'FORTIFY_OPERATION_KUBECTL=fake_kubectl; '
                'fake_kubectl() { case "$*" in *" get statefulset "*) return 1 ;; esac; printf "SCALE:%s\n" "$*"; }; '
                'fortify_scale_statefulset_if_exists fortify missing-statefulset 0',
                "scale-helper-test",
                str(helper),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('statefulset.apps "missing-statefulset" not found', result.stdout)
        self.assertNotIn("SCALE:", result.stdout)

    def test_helm_delete_helper_treats_missing_release_as_success(self) -> None:
        helper = ROOT / "scripts/lib/k8s-destroy.sh"
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; '
                'microk8s() { case "$*" in *" status "*) return 1 ;; esac; printf "DELETE:%s\n" "$*"; }; '
                'fortify_helm_delete_if_exists fortify sdast-scanner',
                "destroy-helper-test",
                str(helper),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('release "sdast-scanner" already absent', result.stdout)
        self.assertNotIn("DELETE:", result.stdout)

    def test_full_lab_destroy_runs_all_destroy_scripts_in_reverse_order(self) -> None:
        result = self.run_wizard_functions(
            'fortify_lab_show_action_warning() { :; }; '
            'run_app_scripts() { printf "RUN:%s\n" "$1"; return 0; }; '
            'wizard_log_event() { :; }; '
            'read _lab_ack; lab_destroy_deployments all; printf "RC=%s\n" "$?"',
            "DESTROY FORTIFY LAB\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        runs = [line.removeprefix("RUN:") for line in result.stdout.splitlines() if line.startswith("RUN:")]
        self.assertEqual(runs, [
            "apps/scdast/core/destroy.sh apps/scdast/scanner/destroy.sh",
            "apps/scsast/destroy.sh",
            "apps/lim/destroy.sh",
            "apps/ssc/destroy.sh",
            "apps/postgresql/destroy.sh",
            "apps/mysql/destroy.sh",
        ])
        self.assertIn("RC=0", result.stdout)

    def test_live_plan_uses_guided_registry_and_labels_impact(self) -> None:
        self.assertIn("wizard_deployment_plan()", WIZARD)
        self.assertIn('for idx in "${!GUIDED_STEP_ID[@]}"', WIZARD)
        self.assertIn("GUIDED_STEP_DURATION=", WIZARD)
        self.assertIn("GUIDED_STEP_IMPACT=", WIZARD)
        self.assertIn("persistent-data deletion is a separate expert action", WIZARD)


    def test_cluster_profile_defaults_and_menu_are_available(self) -> None:
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        for phrase in (
            'FORTIFY_CLUSTER_PROFILE="local"',
            'FORTIFY_CLUSTER_PROFILE_NAMES="local"',
            'FORTIFY_CLUSTER_PROFILE_LOCAL_STORAGE_CLASS="nfs"',
            'FORTIFY_CLUSTER_PROFILE_LOCAL_INGRESS_MODE="microk8s-traefik"',
        ):
            self.assertIn(phrase, env)
        for phrase in (
            "Cluster profiles and remote readiness",
            "cluster_profile_menu()",
            "cluster_profile_remote_readiness()",
            "Remote SSH checks",
            "never copy secrets or mutate remote hosts",
        ):
            self.assertIn(phrase, WIZARD)

    def test_cluster_profile_context_mismatch_blocks_deployment(self) -> None:
        result = self.run_wizard_functions(
            'wizard_log_event() { :; }; '
            'KUBECTL=mock_kubectl; '
            'mock_kubectl() { case "$*" in "config current-context") printf "local-context\\n" ;; esac; }; '
            'FORTIFY_CLUSTER_PROFILE=remote; '
            'FORTIFY_CLUSTER_PROFILE_REMOTE_KUBE_CONTEXT=remote-context; '
            'cluster_profile_report; cluster_profile_confirm_target_context; printf "RC=%s\\n" "$?"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Selected cluster profile: remote", result.stdout)
        self.assertIn("Kube context:       remote-context", result.stdout)
        self.assertIn("Current context:    local-context", result.stdout)
        self.assertIn("Warning: configured context does not match", result.stdout)
        self.assertIn("RC=1", result.stdout)
        self.assertIn("expects kube context 'remote-context'", result.stderr)

    def test_remote_readiness_is_ssh_batch_read_only(self) -> None:
        remote_body = WIZARD.split("cluster_profile_remote_readiness()", 1)[1].split("cluster_profile_diagnostics()", 1)[0]
        self.assertIn("ssh -o BatchMode=yes -o ConnectTimeout=5", remote_body)
        for command in ("docker", "microk8s", "kubectl", "helm", "snap"):
            self.assertIn(command, remote_body)
        for mutating_command in ("scp ", "rsync ", "apt install", "snap install", "kubectl apply", "microk8s enable"):
            self.assertNotIn(mutating_command, remote_body)

    def test_diagnostics_bundle_includes_cluster_profile_report(self) -> None:
        helper = (ROOT / "scripts" / "lib" / "operational-help.sh").read_text(encoding="utf-8")
        diagnostics = (ROOT / "docs" / "operations" / "diagnostics.md").read_text(encoding="utf-8")
        self.assertIn("cluster_profile_report", helper)
        self.assertIn("cluster-profile.txt", helper)
        self.assertIn("cluster-profile.txt", diagnostics)
        self.assertIn("release_overlay_report", helper)
        self.assertIn("release-overlays.txt", helper)
        self.assertIn("release-overlays.txt", diagnostics)


if __name__ == "__main__":
    unittest.main()
