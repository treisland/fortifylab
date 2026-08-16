"""Contracts for Fortify Flight Plans catalog, discovery, and wizard integration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/flight-plans.toml"
TOOL = ROOT / "scripts/tools/flight-plans.py"
HELPER = ROOT / "scripts/lib/flight-plans.sh"
DISCOVER = ROOT / "scripts/tools/discover-flight-plans.sh"
WIZARD = ROOT / "start_wizard.sh"


class FlightPlansTests(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(TOOL), *args], cwd=ROOT, check=False, capture_output=True, text=True)

    def run_wizard_functions(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = str(Path(directory) / "config")
            env["HOME"] = str(Path(directory) / "home")
            return subprocess.run(
                [
                    "bash",
                    "-c",
                    'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; title() { :; }; sleep() { :; }; ' + body,
                    "flight-plan-wizard-test",
                    str(WIZARD),
                ],
                cwd=ROOT,
                input="LAB\n" + user_input,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

    def write_discovery_fixtures(self, fixture_dir: Path, family: str = "25.2") -> None:
        fixture_dir.mkdir(parents=True, exist_ok=True)
        hub_payload = {"results": [{"name": f"{family}.0-1"}, {"name": "latest"}], "next": None}
        registry_payload = {"name": "fortifydocker/ssc-webapp", "tags": [f"{family}.1.00010", f"{family}.2.0005", f"{family}.2.0005.518"]}
        for repo in (
            "fortifydocker__helm-ssc__page1.json",
            "fortifydocker__helm-scancentral-sast__page1.json",
            "fortifydocker__scancentral-sast-controller__page1.json",
            "fortifydocker__scancentral-sast-sensor__page1.json",
            "fortifydocker__helm-scancentral-dast-core__page1.json",
            "fortifydocker__helm-scancentral-dast-scanner__page1.json",
            "fortifydocker__helm-lim__page1.json",
        ):
            (fixture_dir / repo).write_text(json.dumps(hub_payload), encoding="utf-8")
        (fixture_dir / "registry__fortifydocker__ssc-webapp__page1.json").write_text(json.dumps(registry_payload), encoding="utf-8")

    def test_catalog_validates_and_lists_only_curated_user_plans_by_default(self) -> None:
        validation = self.run_tool("validate")
        listing = self.run_tool("list")
        all_listing = self.run_tool("list", "--include-candidates")
        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn("fortify-26.2\tFortify 26.2\trecommended", listing.stdout)
        self.assertNotIn("fortify-25.x", listing.stdout)
        self.assertIn("fortify-25.x\tFortify 25.x\tcandidate", all_listing.stdout)

    def test_catalog_keeps_fortify_components_separate_from_database_defaults(self) -> None:
        text = CATALOG.read_text(encoding="utf-8")
        fortify_plan_section = text.split('[flight_plans."fortify-26.2".components]', 1)[1].split("[flight_plans", 1)[0]
        database_section = text.split("[database_defaults]", 1)[1].split("[flight_plans", 1)[0]
        self.assertIn("FORTIFY_SSC_IMAGE_TAG", fortify_plan_section)
        self.assertIn("FORTIFY_SCDAST_CHART_VERSION", fortify_plan_section)
        self.assertNotIn("FORTIFY_MYSQL_IMAGE_TAG", fortify_plan_section)
        self.assertNotIn("FORTIFY_POSTGRES_IMAGE_TAG", fortify_plan_section)
        self.assertIn("FORTIFY_MYSQL_IMAGE_TAG", database_section)
        self.assertIn("FORTIFY_POSTGRES_IMAGE_TAG", database_section)

    def test_env_updates_stage_fortify_component_versions_without_database_versions(self) -> None:
        result = self.run_tool("env-updates", "fortify-26.2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FORTIFY_SSC_CHART_VERSION=26.2.0-1", result.stdout)
        self.assertIn("FORTIFY_SCSAST_WORKER_IMAGE_TAG=25.2.0", result.stdout)
        self.assertNotIn("FORTIFY_MYSQL_IMAGE_TAG", result.stdout)
        self.assertNotIn("FORTIFY_POSTGRES_IMAGE_TAG", result.stdout)

    def test_compare_env_reports_alignment_and_database_separation(self) -> None:
        result = self.run_tool("compare-env", "fortify-26.2", "--env-file", str(ROOT / ".env.example"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FORTIFY_SSC_IMAGE_TAG\taligned", result.stdout)
        self.assertIn("FORTIFY_MYSQL_IMAGE_TAG\tdatabase-separate", result.stdout)

    def test_invalid_catalog_rejects_unknown_status_and_missing_database_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "flight-plans.toml"
            catalog.write_text(
                textwrap.dedent(
                    '''
                    schema_version = 1
                    default_flight_plan = "broken"

                    [flight_plans.broken]
                    label = "Broken"
                    status = "promoted"

                    [flight_plans.broken.components]
                    FORTIFY_SSC_CHART_VERSION = "1"
                    '''
                ),
                encoding="utf-8",
            )
            result = subprocess.run(["python3", str(TOOL), "--catalog", str(catalog), "validate"], cwd=ROOT, check=False, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be", result.stderr)
        self.assertIn("missing component key FORTIFY_SSC_IMAGE_TAG", result.stderr)
        self.assertIn("database_defaults: missing FORTIFY_MYSQL_IMAGE_TAG", result.stderr)

    def test_discovery_uses_mocked_docker_hub_json_and_writes_candidate_only(self) -> None:
        payload = {"results": [{"name": "26.2.0-1"}, {"name": "26.1.0"}, {"name": "latest"}], "next": None}
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            fixture_dir.mkdir()
            for repo in (
                "fortifydocker__helm-ssc__page1.json",
                "fortifydocker__ssc-webapp__page1.json",
                "fortifydocker__helm-scancentral-sast__page1.json",
                "fortifydocker__scancentral-sast-controller__page1.json",
                "fortifydocker__scancentral-sast-sensor__page1.json",
                "fortifydocker__helm-scancentral-dast-core__page1.json",
                "fortifydocker__helm-lim__page1.json",
            ):
                (fixture_dir / repo).write_text(json.dumps(payload), encoding="utf-8")
            output = Path(directory) / "candidate.toml"
            result = self.run_tool("discover", "--release", "26.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
            candidate = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('status = "candidate"', candidate)
        self.assertNotIn('status = "recommended"', candidate)
        self.assertIn('FORTIFY_SSC_CHART_VERSION = "26.2.0-1"', candidate)
        self.assertIn("Candidate components:", result.stdout)
        self.assertIn("FORTIFY_SCSAST_CTRL_IMAGE_TAG=26.2.0-1", result.stdout)
        self.assertIn("Wrote candidate Flight Plan draft", result.stdout)

    def test_discovery_reuses_catalog_values_when_repo_listing_is_unavailable(self) -> None:
        payload = {"results": [{"name": "26.2.0-1"}], "next": None}
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            fixture_dir.mkdir()
            for repo in (
                "fortifydocker__helm-ssc__page1.json",
                "fortifydocker__helm-scancentral-sast__page1.json",
                "fortifydocker__scancentral-sast-controller__page1.json",
                "fortifydocker__scancentral-sast-sensor__page1.json",
                "fortifydocker__helm-scancentral-dast-core__page1.json",
                "fortifydocker__helm-lim__page1.json",
            ):
                (fixture_dir / repo).write_text(json.dumps(payload), encoding="utf-8")
            output = Path(directory) / "candidate.toml"
            result = self.run_tool("discover", "--release", "26.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
            candidate = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FORTIFY_SSC_IMAGE_TAG = "26.2.0.0183"', candidate)
        self.assertIn('FORTIFY_SCSAST_CTRL_IMAGE_TAG = "26.2.0-1"', candidate)
        self.assertIn('FORTIFY_SCSAST_WORKER_IMAGE_TAG = "26.2.0-1"', candidate)
        self.assertIn("reused catalog value", result.stdout)
        self.assertNotIn("FORTIFY_SSC_IMAGE_TAG: FORTIFY_SSC_IMAGE_TAG", result.stdout)

    def test_discovery_can_use_registry_tag_fixture_when_hub_api_is_unavailable(self) -> None:
        payload = {"results": [{"name": "25.2.0-1"}], "next": None}
        registry_payload = {"name": "fortifydocker/ssc-webapp", "tags": ["25.2.1.00010", "25.2.2.0005", "25.2.2.0005.518"]}
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            fixture_dir.mkdir()
            for repo in (
                "fortifydocker__helm-ssc__page1.json",
                "fortifydocker__helm-scancentral-sast__page1.json",
                "fortifydocker__scancentral-sast-controller__page1.json",
                "fortifydocker__scancentral-sast-sensor__page1.json",
                "fortifydocker__helm-scancentral-dast-core__page1.json",
                "fortifydocker__helm-lim__page1.json",
            ):
                (fixture_dir / repo).write_text(json.dumps(payload), encoding="utf-8")
            (fixture_dir / "registry__fortifydocker__ssc-webapp__page1.json").write_text(json.dumps(registry_payload), encoding="utf-8")
            output = Path(directory) / "candidate.toml"
            result = self.run_tool("discover", "--release", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
            candidate = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FORTIFY_SSC_IMAGE_TAG = "25.2.2.0005.518"', candidate)
        self.assertIn('FORTIFY_SCSAST_CTRL_IMAGE_TAG = "25.2.0-1"', candidate)
        self.assertIn('FORTIFY_SCSAST_WORKER_IMAGE_TAG = "25.2.0-1"', candidate)
        self.assertIn("INFO: FORTIFY_SSC_IMAGE_TAG: selected from authenticated Docker Registry API", result.stdout)
        self.assertNotIn("WARNING: FORTIFY_SSC_IMAGE_TAG", result.stdout)

    def test_discovery_maps_scancentral_repositories(self) -> None:
        tool = TOOL.read_text(encoding="utf-8")
        self.assertIn('"FORTIFY_SCSAST_CTRL_IMAGE_TAG": ("fortifydocker/scancentral-sast-controller",)', tool)
        self.assertIn('"FORTIFY_SCSAST_WORKER_IMAGE_TAG": ("fortifydocker/scancentral-sast-sensor",)', tool)
        self.assertIn('"FORTIFY_SCDAST_CHART_VERSION": (', tool)
        self.assertIn('"fortifydocker/helm-scancentral-dast-core"', tool)
        self.assertIn('"fortifydocker/helm-scancentral-dast-scanner"', tool)

    def test_discover_releases_scores_release_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            result = self.run_tool("discover-releases", "--years", "25", "--fixture-dir", str(fixture_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Discovered Fortify releases", result.stdout)
        self.assertIn("25.2", result.stdout)
        self.assertIn("7/7", result.stdout)
        self.assertIn("candidate ready", result.stdout)
        self.assertNotIn("26.2", result.stdout)

    def test_discover_releases_does_not_count_missing_component_release_tags(self) -> None:
        old_payload = {"results": [{"name": "22.1.0-1"}], "next": None}
        dast_payload = {"results": [{"name": "24.4.0-2"}], "next": None}
        registry_payload = {"name": "fortifydocker/ssc-webapp", "tags": ["22.1.0.0001"]}
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            fixture_dir.mkdir()
            for repo in (
                "fortifydocker__helm-ssc__page1.json",
                "fortifydocker__helm-scancentral-sast__page1.json",
                "fortifydocker__scancentral-sast-controller__page1.json",
                "fortifydocker__scancentral-sast-sensor__page1.json",
                "fortifydocker__helm-lim__page1.json",
            ):
                (fixture_dir / repo).write_text(json.dumps(old_payload), encoding="utf-8")
            for repo in (
                "fortifydocker__helm-scancentral-dast-core__page1.json",
                "fortifydocker__helm-scancentral-dast-scanner__page1.json",
            ):
                (fixture_dir / repo).write_text(json.dumps(dast_payload), encoding="utf-8")
            (fixture_dir / "registry__fortifydocker__ssc-webapp__page1.json").write_text(json.dumps(registry_payload), encoding="utf-8")
            result = self.run_tool("discover-releases", "--years", "22", "--fixture-dir", str(fixture_dir))
            candidate = Path(directory) / "fortify-22.1.toml"
            write_result = self.run_tool(
                "discover-releases",
                "--years",
                "22",
                "--write-complete",
                "--output-dir",
                str(Path(directory) / "candidates"),
                "--fixture-dir",
                str(fixture_dir),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("22.1", result.stdout)
        self.assertIn("6/7", result.stdout)
        self.assertIn("needs review", result.stdout)
        self.assertEqual(write_result.returncode, 0, write_result.stderr)
        self.assertIn("Candidate files written: 0", write_result.stdout)
        self.assertFalse(candidate.exists())

    def test_discover_releases_can_write_complete_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            output_dir = Path(directory) / "candidates"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            result = self.run_tool(
                "discover-releases",
                "--years",
                "25",
                "--write-complete",
                "--output-dir",
                str(output_dir),
                "--fixture-dir",
                str(fixture_dir),
            )
            candidate = output_dir / "fortify-25.2.toml"
            candidate_exists = candidate.exists()
            candidate_text = candidate.read_text(encoding="utf-8") if candidate_exists else ""
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(candidate_exists)
        self.assertIn("Candidate files written: 1", result.stdout)
        self.assertIn('FORTIFY_SSC_IMAGE_TAG = "25.2.2.0005.518"', candidate_text)
        self.assertIn('FORTIFY_SCSAST_WORKER_IMAGE_TAG = "25.2.0-1"', candidate_text)

    def test_old_discovery_names_remain_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            candidate = Path(directory) / "fortify-25.2.toml"
            discover = self.run_tool("discover", "--family", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(candidate))
            releases = self.run_tool("discover-families", "--years", "25", "--fixture-dir", str(fixture_dir))
        self.assertEqual(discover.returncode, 0, discover.stderr)
        self.assertEqual(releases.returncode, 0, releases.stderr)
        self.assertIn("Discovered Fortify releases", releases.stdout)

    def test_curate_prints_repo_owner_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            result = self.run_tool("curate", "--years", "25", "--fixture-dir", str(fixture_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Curator workflow", result.stdout)
        self.assertIn("flight-plans.py discover --release <release>", result.stdout)
        self.assertIn("flight-plans.py promote tmp/flight-plan-candidates/fortify-<release>.toml --status candidate --yes", result.stdout)
        self.assertIn("Complete candidate releases: 25.2", result.stdout)

    def test_promote_candidate_supports_dry_run_without_catalog_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            candidate = Path(directory) / "fortify-25.2.toml"
            discover = self.run_tool("discover", "--release", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(candidate))
            catalog = Path(directory) / "flight-plans.toml"
            shutil.copyfile(CATALOG, catalog)
            before = catalog.read_text(encoding="utf-8")
            result = self.run_tool("--catalog", str(catalog), "promote", str(candidate), "--status", "candidate")
            after = catalog.read_text(encoding="utf-8")
        self.assertEqual(discover.returncode, 0, discover.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, after)
        self.assertIn("Dry run only", result.stdout)

    def test_promote_candidate_can_update_temp_catalog_and_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            candidate = Path(directory) / "fortify-25.2.toml"
            discover = self.run_tool("discover", "--release", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(candidate))
            catalog = Path(directory) / "flight-plans.toml"
            shutil.copyfile(CATALOG, catalog)
            result = self.run_tool("--catalog", str(catalog), "promote", str(candidate), "--status", "recommended", "--yes")
            validation = self.run_tool("--catalog", str(catalog), "validate")
            updated = catalog.read_text(encoding="utf-8")
        self.assertEqual(discover.returncode, 0, discover.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertIn('default_flight_plan = "fortify-25.2"', updated)
        self.assertIn('[flight_plans."fortify-25.2"]', updated)
        self.assertIn('status = "recommended"', updated)
        self.assertIn('[flight_plans."fortify-26.2"]', updated)
        self.assertIn('status = "known-good"', updated)

    def test_top_level_help_groups_workflows_and_safety_model(self) -> None:
        result = self.run_tool("-h")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Command groups:", result.stdout)
        self.assertIn("Lab operators:", result.stdout)
        self.assertIn("Repo-owner curation:", result.stdout)
        self.assertIn("Safety model:", result.stdout)
        self.assertIn("flight-plans.py discover-releases --years 25,26", result.stdout)
        self.assertIn("Release      A Fortify yy.quarter line", result.stdout)

    def test_subcommand_help_explains_operator_commands(self) -> None:
        list_help = self.run_tool("list", "-h")
        compare_help = self.run_tool("compare-env", "-h")
        env_help = self.run_tool("env-updates", "-h")
        self.assertEqual(list_help.returncode, 0, list_help.stderr)
        self.assertEqual(compare_help.returncode, 0, compare_help.stderr)
        self.assertEqual(env_help.returncode, 0, env_help.stderr)
        self.assertIn("Candidate plans are hidden by default", list_help.stdout)
        self.assertIn("Exit codes:", compare_help.stdout)
        self.assertIn("Secrets are not printed", compare_help.stdout)
        self.assertIn("does not edit .env", env_help.stdout)

    def test_subcommand_help_explains_owner_commands(self) -> None:
        discover_help = self.run_tool("discover", "-h")
        releases_help = self.run_tool("discover-releases", "-h")
        promote_help = self.run_tool("promote", "-h")
        curate_help = self.run_tool("curate", "-h")
        self.assertEqual(discover_help.returncode, 0, discover_help.stderr)
        self.assertEqual(releases_help.returncode, 0, releases_help.stderr)
        self.assertEqual(promote_help.returncode, 0, promote_help.stderr)
        self.assertEqual(curate_help.returncode, 0, curate_help.stderr)
        self.assertIn("--release RELEASE, --family RELEASE", discover_help.stdout)
        self.assertIn("Compatibility:", discover_help.stdout)
        self.assertIn("score candidate Flight Plan coverage", releases_help.stdout)
        self.assertIn("--write-complete", releases_help.stdout)
        self.assertIn("Dry run is the default", promote_help.stdout)
        self.assertIn("--yes writes config/flight-plans.toml", promote_help.stdout)
        self.assertIn("drafting, reviewing, promoting, and validating", curate_help.stdout)

    def test_shell_wrappers_delegate_to_single_catalog_implementation(self) -> None:
        result = subprocess.run(
            ["bash", "-c", 'FORTIFY_HOME_K8S="$PWD"; source scripts/lib/flight-plans.sh; flight_plan_validate_catalog; flight_plan_list'],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fortify-26.2", result.stdout)

    def test_wizard_stages_selected_flight_plan_with_existing_env_backup_flow(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$PWD"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'cp .env.example "$ENV_FILE"; source "$ENV_FILE"; read -r _lab_ack; pending=(); '
            'flight_plan_stage_updates pending fortify-26.2; env_preview_changes "${pending[@]}"; printf "COUNT=%s\\n" "${#pending[@]}"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FORTIFY_FLIGHT_PLAN", result.stdout)
        self.assertIn("FORTIFY_SSC_IMAGE_TAG", result.stdout)
        self.assertIn("COUNT=8", result.stdout)

    def test_guided_setup_can_stage_flight_plan_selection_without_immediate_apply(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$PWD"; ENV_FILE="$tmp/.env"; ENV_BACKUP_DIR="$tmp/.env.backups"; '
            'cp .env.example "$ENV_FILE"; source "$ENV_FILE"; read -r _lab_ack; '
            'setup_flight_plan_assistant; env_preview_changes "${SETUP_PENDING_UPDATES[@]}"',
            user_input="1\n1\n\nb\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Flight Plan staged: Fortify 26.2", result.stdout)
        self.assertIn("FORTIFY_FLIGHT_PLAN", result.stdout)
        self.assertIn("FORTIFY_SSC_IMAGE_TAG", result.stdout)


    def test_release_overlay_report_treats_missing_overlays_as_normal(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; FORTIFY_FLIGHT_PLAN=fortify-26.2; release_overlay_report'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Selected Flight Plan: fortify-26.2", result.stdout)
        self.assertIn("Selected release overlay baseline: 26.2", result.stdout)
        self.assertIn("Release overlays:", result.stdout)
        self.assertIn("SSC", result.stdout)
        self.assertIn("none for release 26.2", result.stdout)

    def test_release_overlay_loads_selected_shell_overlay_helm_args(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; FORTIFY_FLIGHT_PLAN=fortify-26.2; '
            'mkdir -p "$tmp/apps/ssc/releases/26.2"; '
            'printf "%s\n" "RELEASE_OVERLAY_HELM_ARGS+=(--set-string release.overlay=26.2)" >"$tmp/apps/ssc/releases/26.2/overrides.sh"; '
            'release_overlay_load ssc; printf "ARGS=%s\n" "${RELEASE_OVERLAY_HELM_ARGS[*]}"; release_overlay_report'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ARGS=--set-string release.overlay=26.2", result.stdout)
        self.assertIn("apps/ssc/releases/26.2/overrides.sh", result.stdout)

    def test_ssc_25_2_overlay_maps_required_secretref_keys(self) -> None:
        result = subprocess.run(
            [
                "bash",
                "-c",
                'FORTIFY_HOME_K8S="$PWD" FORTIFY_FLIGHT_PLAN=fortify-25.2; '
                'source scripts/lib/release-overlays.sh; '
                'release_overlay_load ssc; printf "%s\n" "${RELEASE_OVERLAY_HELM_ARGS[@]}"',
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("secretRef.name=fortify-secrets", result.stdout)
        self.assertIn("secretRef.keys.sscLicenseEntry=fortify.license", result.stdout)
        self.assertIn("secretRef.keys.sscAutoconfigEntry=ssc.autoconfig", result.stdout)
        self.assertIn("secretRef.keys.httpCertificateKeystoreFileEntry=keystore.jks", result.stdout)
        self.assertIn("secretRef.keys.httpCertificateKeyPasswordEntry=key_password", result.stdout)
        self.assertIn("secretRef.keys.httpCertificateKeystorePasswordEntry=keystore_password", result.stdout)

    def test_release_overlay_validate_selected_detects_shell_syntax_errors(self) -> None:
        result = self.run_wizard_functions(
            'tmp=$(mktemp -d); FORTIFY_HOME_K8S="$tmp"; FORTIFY_FLIGHT_PLAN=fortify-26.2; '
            'mkdir -p "$tmp/apps/ssc/releases/26.2"; '
            'printf "%s\n" "if then" >"$tmp/apps/ssc/releases/26.2/overrides.sh"; '
            'release_overlay_validate_selected; printf "RC=%s\n" "$?"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("syntax error", result.stderr)
        self.assertIn("RC=1", result.stdout)

    def test_deployment_inputs_and_diagnostics_surface_flight_plan_context(self) -> None:
        guided = (ROOT / "scripts/wizard/guided.sh").read_text(encoding="utf-8")
        operations = (ROOT / "scripts/wizard/operations.sh").read_text(encoding="utf-8")
        self.assertIn("Deployment versions and Flight Plan", guided)
        self.assertIn("Flight Plan:", guided)
        self.assertIn('section "Flight Plan"', guided)
        self.assertIn("flight_plan_show_comparison", operations)
        self.assertIn("release_overlay_report", guided)
        self.assertIn("release_overlay_validate_selected", guided)
        self.assertIn("release_overlay_report", operations)


if __name__ == "__main__":
    unittest.main()
