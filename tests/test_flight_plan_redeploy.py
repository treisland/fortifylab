"""Contracts for redeploying after a Flight Plan change: deployed-version
detection, the wizard banner, rollout-aware verification, per-product release
overlays, the downgrade guard, and the ordered redeploy flow."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/tools/flight-plans.py"
WIZARD = ROOT / "start_wizard.sh"
DEPLOYED_LIB = ROOT / "scripts/lib/deployed-versions.sh"
HEALTH_LIB = ROOT / "scripts/lib/dependency-health.sh"
OVERLAY_LIB = ROOT / "scripts/lib/release-overlays.sh"
REPO_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "tmp", ".fortifylab", ".env.backups", ".env.rollback",
    "flight-plans.local.toml", "flight-plans.local.toml.bak",
)

# Running versions of a lab on Flight Plan fortify-26.2, except DAST, which
# still runs 24.3.0-1 after the plan moved it to 24.4.0-2.
FAKE_CLUSTER = textwrap.dedent(
    r"""
    fake_helm() {
        [ "${FAKE_HELM_FAIL:-0}" = 1 ] && return 1
        cat <<'JSON'
    [{"name":"ssc","status":"deployed","chart":"helm-ssc-26.2.0-1"},
     {"name":"lim","status":"deployed","chart":"helm-lim-24.4.0-3"},
     {"name":"mysql","status":"deployed","chart":"mysql-9.19.0"},
     {"name":"scancentral-sast","status":"deployed","chart":"helm-scancentral-sast-26.2.0-1"},
     {"name":"sdast-core","status":"deployed","chart":"helm-scancentral-dast-core-24.3.0-1"},
     {"name":"sdast-scanner","status":"deployed","chart":"helm-scancentral-dast-scanner-24.3.0-1"}]
    JSON
    }
    fake_kubectl() {
        local name="$5"
        case "$name" in
            ssc-webapp) printf 'fortifydocker/ssc-webapp:26.2.0.0183' ;;
            scancentral-sast-controller) printf 'fortifydocker/scancentral-sast-controller:26.2.0' ;;
            scancentral-sast-sensor-linux) [ "${FAKE_NO_SENSOR:-0}" = 1 ] && return 1; printf 'fortifydocker/scancentral-sast-sensor:25.2.0' ;;
            *) return 1 ;;
        esac
    }
    HELM=fake_helm; KUBECTL=fake_kubectl; NAMESPACE=fortify
    FORTIFY_SSC_CHART_VERSION=26.2.0-1
    FORTIFY_SSC_IMAGE_TAG=26.2.0.0183
    FORTIFY_SCSAST_CHART_VERSION=26.2.0-1
    FORTIFY_SCSAST_CTRL_IMAGE_TAG=26.2.0
    FORTIFY_SCSAST_WORKER_IMAGE_TAG=25.2.0
    FORTIFY_SCDAST_CHART_VERSION=24.4.0-2
    FORTIFY_LIM_CHART_VERSION=24.4.0-3
    FORTIFY_FLIGHT_PLAN=fortify-26.2
    """
)


class RedeployTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "repo"
        # config + scripts only: the Python tool resolves its catalog next to
        # itself, so the real local catalog never leaks in.
        self.home.mkdir()
        shutil.copytree(ROOT / "config", self.home / "config", ignore=REPO_COPY_IGNORE)
        shutil.copytree(ROOT / "scripts", self.home / "scripts", ignore=REPO_COPY_IGNORE)
        shutil.copytree(ROOT / "apps", self.home / "apps", ignore=REPO_COPY_IGNORE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def bash(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(Path(self._tmp.name) / "home")
        env["FORTIFY_HOME_K8S"] = str(self.home)
        env.pop("FORTIFY_DEPLOYED_VERSIONS", None)
        return subprocess.run(
            ["bash", "-c", body],
            cwd=self.home,
            input=user_input,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def lib(self, body: str) -> subprocess.CompletedProcess[str]:
        return self.bash(f'source "{self.home}/scripts/lib/deployed-versions.sh"\n{FAKE_CLUSTER}\n{body}')

    def wizard(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        # Source the real wizard (it locates its modules from FORTIFY_HOME_K8S).
        shutil.copy(WIZARD, self.home / "start_wizard.sh")
        return self.bash(
            'export WIZARD_NOMAIN=1 NO_COLOR=1; source ./start_wizard.sh; '
            'title() { :; }; sleep() { :; }; press_any() { :; }\n'
            f"{FAKE_CLUSTER}\n{body}",
            user_input,
        )

    def tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(self.home / "scripts/tools/flight-plans.py"), *args],
            check=False, capture_output=True, text=True,
        )

    def write_local_plan(self, plan_id: str, family: str, components: dict[str, str]) -> None:
        lines = ["schema_version = 1", "", f'[flight_plans."{plan_id}"]', f'label = "Fortify {family}"',
                 'status = "known-good"', f'family = "{family}"', "", f'[flight_plans."{plan_id}".components]']
        lines += [f'{key} = "{value}"' for key, value in components.items()]
        (self.home / "config/flight-plans.local.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


PLAN_25_2 = {
    "FORTIFY_SSC_CHART_VERSION": "25.2.0-1",
    "FORTIFY_SSC_IMAGE_TAG": "25.2.0.0100",
    "FORTIFY_SCSAST_CHART_VERSION": "25.2.0-1",
    "FORTIFY_SCSAST_CTRL_IMAGE_TAG": "25.2.0",
    "FORTIFY_SCSAST_WORKER_IMAGE_TAG": "25.2.0",
    "FORTIFY_SCDAST_CHART_VERSION": "24.4.0-2",
    "FORTIFY_LIM_CHART_VERSION": "24.4.0-3",
}


class CatalogCommandTests(RedeployTestCase):
    def test_relation_classifies_same_upgrade_downgrade_and_unknown(self) -> None:
        self.write_local_plan("fortify-25.2", "25.2", PLAN_25_2)
        self.assertEqual(self.tool("relation", "fortify-26.2", "fortify-25.2").stdout.strip(), "downgrade")
        self.assertEqual(self.tool("relation", "fortify-25.2", "fortify-26.2").stdout.strip(), "upgrade")
        self.assertEqual(self.tool("relation", "fortify-26.2", "fortify-26.2").stdout.strip(), "same")
        self.assertEqual(self.tool("relation", "fortify-26.2", "no-such-plan").stdout.strip(), "unknown")

    def test_match_running_names_plan_custom_or_unknown(self) -> None:
        values = Path(self._tmp.name) / "running"
        values.write_text("state=ok\nFORTIFY_SSC_CHART_VERSION=26.2.0-1\nFORTIFY_LIM_CHART_VERSION=24.4.0-3\n", encoding="utf-8")
        self.assertEqual(self.tool("match-running", "--values-file", str(values)).stdout.strip(), "fortify-26.2")
        values.write_text("FORTIFY_SSC_CHART_VERSION=26.2.0-1\nFORTIFY_SCDAST_CHART_VERSION=24.3.0-1\n", encoding="utf-8")
        self.assertEqual(self.tool("match-running", "--values-file", str(values)).stdout.strip(), "custom")
        values.write_text("state=unreachable\n", encoding="utf-8")
        self.assertEqual(self.tool("match-running", "--values-file", str(values)).stdout.strip(), "unknown")

    def test_family_tag_matching_requires_a_separator(self) -> None:
        result = subprocess.run(
            ["python3", "-c", textwrap.dedent(f"""
                import importlib.util, sys
                spec = importlib.util.spec_from_file_location("fp", "{TOOL}")
                fp = importlib.util.module_from_spec(spec); sys.modules["fp"] = fp; spec.loader.exec_module(fp)
                print(fp.tag_in_family("26.2.0-1", "26.2"), fp.tag_in_family("26.20.0", "26.2"),
                      fp.tag_in_family("25.2.0", "25"), fp.tag_in_family("250.1", "25"), fp.tag_in_family("26.2", "26.2"))
            """)],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.stdout.split(), ["True", "False", "True", "False", "True"], result.stderr)

    def test_show_marks_local_plans_and_promote_keeps_extra_fields(self) -> None:
        self.write_local_plan("fortify-26.2", "26.2", PLAN_25_2)
        show = self.tool("show", "fortify-26.2")
        self.assertIn("Source:      local catalog (overrides the curated plan with the same id)", show.stdout)
        candidate = Path(self._tmp.name) / "candidate.toml"
        candidate.write_text(textwrap.dedent("""
            schema_version = 1
            [flight_plans."fortify-26.3"]
            label = "Fortify 26.3"
            status = "candidate"
            family = "26.3"
            tested_by = "lab-team"
            [flight_plans."fortify-26.3".components]
        """) + "\n".join(f'{k} = "1"' for k in PLAN_25_2) + "\n", encoding="utf-8")
        result = self.tool("promote", str(candidate), "--status", "known-good", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('tested_by = "lab-team"', (self.home / "config/flight-plans.toml").read_text(encoding="utf-8"))


class DeployedVersionTests(RedeployTestCase):
    def test_refresh_detects_stale_component_and_running_plan(self) -> None:
        result = self.lib(
            "deployed_versions_refresh; "
            "for c in ssc lim sast dast; do echo \"$c=$(deployed_status_for $c)\"; done; "
            "echo \"detail=$(deployed_stale_detail dast)\"; "
            "echo \"order=$(deployed_components_needing_redeploy | paste -sd, -)\"; "
            "echo \"plan=$(deployed_flight_plan)\""
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in ("ssc=current", "lim=current", "sast=current", "dast=needs-redeploy", "order=dast", "plan=custom"):
            self.assertIn(line, result.stdout)
        self.assertIn("detail=DAST core chart 24.3.0-1 -> 24.4.0-2; DAST scanner chart 24.3.0-1 -> 24.4.0-2", result.stdout)

    def test_matching_cluster_reports_running_plan(self) -> None:
        result = self.lib(
            "FORTIFY_SCDAST_CHART_VERSION=24.3.0-1; "
            "fake_helm() { printf '%s' '[{\"name\":\"ssc\",\"status\":\"deployed\",\"chart\":\"helm-ssc-26.2.0-1\"}]'; }; "
            "deployed_versions_refresh; echo \"plan=$(deployed_flight_plan)\"; deployed_versions_banner"
        )
        self.assertIn("plan=fortify-26.2", result.stdout)
        self.assertIn("Flight Plan fortify-26.2 · deployed and current (checked just now)", result.stdout)

    def test_failed_helm_release_is_never_current(self) -> None:
        result = self.lib(
            "fake_helm() { printf '%s' '[{\"name\":\"lim\",\"status\":\"failed\",\"chart\":\"helm-lim-24.4.0-3\"}]'; }; "
            "deployed_versions_refresh; deployed_status_for lim"
        )
        self.assertEqual(result.stdout.strip(), "needs-redeploy")

    def test_controller_only_sast_is_current_without_sensor(self) -> None:
        result = self.lib("FAKE_NO_SENSOR=1; deployed_versions_refresh; deployed_status_for sast; deployed_check_status sast_worker_image")
        self.assertEqual(result.stdout.split(), ["current", "not-deployed"])

    def test_unreachable_cluster_reports_unknown_and_banner_says_so(self) -> None:
        result = self.lib("FAKE_HELM_FAIL=1; deployed_versions_refresh; echo \"rc=$?\"; deployed_status_for ssc; deployed_versions_banner")
        self.assertIn("rc=1", result.stdout)
        self.assertIn("unknown", result.stdout)
        self.assertIn("deployed version unknown (cluster unreachable", result.stdout)

    def test_banner_names_products_needing_redeploy(self) -> None:
        result = self.lib("deployed_versions_refresh; deployed_versions_banner")
        self.assertIn(
            "Flight Plan: selected fortify-26.2 · running custom versions · 1 of 4 products need redeploy (DAST)",
            result.stdout,
        )

    def test_banner_and_lookups_can_be_disabled(self) -> None:
        result = self.lib("FORTIFY_DEPLOYED_VERSIONS=off; deployed_versions_refresh; echo \"rc=$?\"; deployed_versions_banner; deployed_status_for ssc")
        self.assertEqual(result.stdout.split(), ["rc=1", "unknown"])

    def test_cache_is_reused_within_ttl(self) -> None:
        result = self.lib(
            "deployed_versions_refresh; FAKE_HELM_FAIL=1; deployed_versions_ensure_fresh 300; deployed_versions_state"
        )
        self.assertEqual(result.stdout.strip(), "ok")


class HealthAndOverlayTests(RedeployTestCase):
    def health(self, fields: str) -> subprocess.CompletedProcess[str]:
        return self.bash(textwrap.dedent(f"""
            source "{HEALTH_LIB}"
            KUBECTL=fake_kubectl; NAMESPACE=fortify
            fake_kubectl() {{
                case "$*" in
                    *spec.replicas*) printf 1 ;;
                    *readyReplicas*) printf 1 ;;
                    *currentReplicas*) printf 1 ;;
                    *metadata.generation*) printf '%s' '{fields}' ;;
                esac
            }}
            health_statefulset_ready ssc-webapp; echo "rc=$?"
        """))

    def test_statefulset_is_not_ready_until_rollout_completes(self) -> None:
        self.assertIn("rc=0", self.health("3|3|ssc-new|ssc-new").stdout)
        self.assertIn("rc=1", self.health("3|3|ssc-old|ssc-new").stdout)
        self.assertIn("rc=1", self.health("4|3|ssc-old|ssc-old").stdout)

    def test_component_override_selects_overlay_for_its_own_chart_release(self) -> None:
        result = self.bash(
            f'source "{OVERLAY_LIB}"; FORTIFY_FLIGHT_PLAN=fortify-26.2; '
            "FORTIFY_SSC_CHART_VERSION=25.2.0-1; FORTIFY_LIM_CHART_VERSION=24.4.0-3; "
            "release_overlay_release_for_app ssc; release_overlay_release_for_app lim; "
            "RELEASE_OVERLAY_ASSUME_PLAN=1 release_overlay_release_for_app ssc; "
            "release_overlay_load ssc; printf '%s\\n' \"${RELEASE_OVERLAY_HELM_ARGS[@]}\" | grep -c secretRef"
        )
        lines = result.stdout.split()
        self.assertEqual(lines[:3], ["25.2", "26.2", "26.2"], result.stderr)
        self.assertGreater(int(lines[3]), 0)


class WizardRedeployTests(RedeployTestCase):
    def test_guided_step_is_incomplete_while_running_versions_are_stale(self) -> None:
        result = self.wizard(
            "ssc_ready() { return 0; }; dast_scanner_ready() { return 0; }; "
            "guided_step_complete ssc; echo \"ssc=$?\"; "
            "guided_step_complete dast_scanner; echo \"dast=$?\"; "
            "echo \"why=$(guided_step_why_pending dast_scanner)\""
        )
        self.assertIn("ssc=0", result.stdout, result.stderr)
        self.assertIn("dast=1", result.stdout)
        self.assertIn("why=Running versions differ from .env (DAST scanner chart 24.3.0-1 -> 24.4.0-2)", result.stdout)

    def test_unknown_versions_leave_health_in_charge(self) -> None:
        result = self.wizard("FAKE_HELM_FAIL=1; dast_scanner_ready() { return 0; }; guided_step_complete dast_scanner; echo \"rc=$?\"")
        self.assertIn("rc=0", result.stdout, result.stderr)

    def test_redeploy_runs_only_stale_products_in_dependency_order(self) -> None:
        result = self.wizard(
            "FORTIFY_SSC_IMAGE_TAG=26.2.1.0001; "
            "guided_run_and_verify() { echo \"RUN $1\"; }; wizard_log_event() { :; }; "
            "flight_plan_redeploy_stale yes"
        )
        runs = [line for line in result.stdout.splitlines() if line.startswith("RUN ")]
        self.assertEqual(runs, ["RUN ssc", "RUN dast_core", "RUN dast_scanner"], result.stdout + result.stderr)
        self.assertIn("Redeploy complete", result.stdout)

    def test_redeploy_stops_at_first_failure(self) -> None:
        result = self.wizard(
            "FORTIFY_SSC_IMAGE_TAG=26.2.1.0001; "
            "guided_run_and_verify() { echo \"RUN $1\"; [ \"$1\" != ssc ]; }; wizard_log_event() { :; }; "
            "flight_plan_redeploy_stale yes; echo \"rc=$?\""
        )
        self.assertIn("RUN ssc", result.stdout)
        self.assertNotIn("RUN dast_core", result.stdout)
        self.assertIn("rc=1", result.stdout)
        self.assertIn("Redeploy stopped at", result.stderr)

    def test_redeploy_prompt_can_be_declined(self) -> None:
        result = self.wizard(
            "guided_run_and_verify() { echo \"RUN $1\"; }; flight_plan_redeploy_stale",
            user_input="n\n",
        )
        self.assertNotIn("RUN ", result.stdout)
        self.assertIn("Not redeployed", result.stdout)

    def test_interactive_downgrade_requires_typing_the_plan_id(self) -> None:
        self.write_local_plan("fortify-25.2", "25.2", PLAN_25_2)
        body = "FORTIFY_DEPLOYED_VERSIONS=off; flight_plan_confirm_downgrade fortify-25.2; echo \"rc=$?\""
        refused = self.wizard(body, user_input="y\n")
        accepted = self.wizard(body, user_input="fortify-25.2\n")
        self.assertIn("Downgrade warning", refused.stdout)
        self.assertIn("rc=1", refused.stdout)
        self.assertIn("rc=0", accepted.stdout)

    def test_full_plan_staging_clears_component_drift_marker(self) -> None:
        result = self.wizard(
            "pending=(FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS=ssc); "
            "flight_plan_stage_updates pending fortify-26.2; printf '%s\\n' \"${pending[@]}\""
        )
        self.assertIn("FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS=\n", result.stdout + "\n")
        self.assertNotIn("FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS=ssc", result.stdout)


class ApplyCliTests(RedeployTestCase):
    def run_cli(self, *args: str) -> tuple[subprocess.CompletedProcess[str], str, list[Path]]:
        home = Path(self._tmp.name) / "full"
        if not home.exists():
            shutil.copytree(ROOT, home, ignore=REPO_COPY_IGNORE)
            shutil.copy(home / ".env.example", home / ".env")
            shutil.copy(self.home / "config/flight-plans.local.toml", home / "config/flight-plans.local.toml")
        env = os.environ.copy()
        env["HOME"] = str(Path(self._tmp.name) / "home")
        env["FORTIFY_DEPLOYED_VERSIONS"] = "off"
        env.pop("FORTIFY_HOME_K8S", None)
        result = subprocess.run([str(home / "start_wizard.sh"), *args], cwd=home, check=False,
                                capture_output=True, text=True, env=env)
        backups = list((home / ".env.backups").glob("*.bak")) if (home / ".env.backups").exists() else []
        return result, (home / ".env").read_text(encoding="utf-8"), backups

    def test_cli_downgrade_needs_allow_downgrade(self) -> None:
        self.write_local_plan("fortify-25.2", "25.2", PLAN_25_2)
        dry, _env, _backups = self.run_cli("apply-flight-plan", "fortify-25.2")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("will also require --allow-downgrade", dry.stdout)
        refused, env_after, backups = self.run_cli("apply-flight-plan", "fortify-25.2", "--yes")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("without --allow-downgrade", refused.stderr)
        self.assertEqual(backups, [])
        self.assertNotIn("fortify-25.2", env_after)
        allowed, env_after, backups = self.run_cli("apply-flight-plan", "fortify-25.2", "--yes", "--allow-downgrade")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertIn("FORTIFY_FLIGHT_PLAN='fortify-25.2'", env_after)
        self.assertEqual(len(backups), 1)

    def test_cli_redeploy_flag_is_accepted_and_reports_unreachable_cluster(self) -> None:
        self.write_local_plan("fortify-25.2", "25.2", PLAN_25_2)
        result, _env, _backups = self.run_cli("apply-flight-plan", "fortify-26.2", "--yes", "--redeploy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Could not read deployed versions", result.stdout)

    def test_cli_rejects_flags_in_place_of_plan_id(self) -> None:
        self.write_local_plan("fortify-25.2", "25.2", PLAN_25_2)
        result, _env, _backups = self.run_cli("apply-flight-plan", "--yes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ./start_wizard.sh apply-flight-plan <plan-id>", result.stderr)

    def test_flight_plan_status_command_is_documented_and_runs(self) -> None:
        self.write_local_plan("fortify-25.2", "25.2", PLAN_25_2)
        result, _env, _backups = self.run_cli("flight-plan-status")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not read deployed versions", result.stdout)
        usage, _env, _backups = self.run_cli("--help")
        self.assertIn("flight-plan-status", usage.stdout)
        self.assertIn("--redeploy", usage.stdout)


if __name__ == "__main__":
    unittest.main()
