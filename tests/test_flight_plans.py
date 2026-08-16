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
            result = self.run_tool("discover", "--family", "26.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
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
            result = self.run_tool("discover", "--family", "26.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
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
            result = self.run_tool("discover", "--family", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
            candidate = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FORTIFY_SSC_IMAGE_TAG = "25.2.2.0005.518"', candidate)
        self.assertIn('FORTIFY_SCSAST_CTRL_IMAGE_TAG = "25.2.0-1"', candidate)
        self.assertIn('FORTIFY_SCSAST_WORKER_IMAGE_TAG = "25.2.0-1"', candidate)
        self.assertIn("INFO: FORTIFY_SSC_IMAGE_TAG: selected from authenticated Docker Registry API", result.stdout)
        self.assertNotIn("WARNING: FORTIFY_SSC_IMAGE_TAG", result.stdout)

    def test_discovery_maps_scancentral_sast_image_repositories(self) -> None:
        tool = TOOL.read_text(encoding="utf-8")
        self.assertIn('"FORTIFY_SCSAST_CTRL_IMAGE_TAG": "fortifydocker/scancentral-sast-controller"', tool)
        self.assertIn('"FORTIFY_SCSAST_WORKER_IMAGE_TAG": "fortifydocker/scancentral-sast-sensor"', tool)

    def test_discover_families_scores_release_family_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            result = self.run_tool("discover-families", "--years", "25", "--fixture-dir", str(fixture_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Discovered Fortify release families", result.stdout)
        self.assertIn("25.2", result.stdout)
        self.assertIn("7/7", result.stdout)
        self.assertIn("candidate ready", result.stdout)
        self.assertNotIn("26.2", result.stdout)

    def test_discover_families_can_write_complete_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            output_dir = Path(directory) / "candidates"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            result = self.run_tool(
                "discover-families",
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

    def test_curate_prints_repo_owner_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            result = self.run_tool("curate", "--years", "25", "--fixture-dir", str(fixture_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Curator workflow", result.stdout)
        self.assertIn("flight-plans.py discover --family <family>", result.stdout)
        self.assertIn("flight-plans.py promote tmp/flight-plan-candidates/fortify-<family>.toml --status candidate --yes", result.stdout)
        self.assertIn("Complete candidate families: 25.2", result.stdout)

    def test_promote_candidate_supports_dry_run_without_catalog_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            self.write_discovery_fixtures(fixture_dir, family="25.2")
            candidate = Path(directory) / "fortify-25.2.toml"
            discover = self.run_tool("discover", "--family", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(candidate))
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
            discover = self.run_tool("discover", "--family", "25.2", "--fixture-dir", str(fixture_dir), "--output", str(candidate))
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

    def test_deployment_inputs_and_diagnostics_surface_flight_plan_context(self) -> None:
        guided = (ROOT / "scripts/wizard/guided.sh").read_text(encoding="utf-8")
        operations = (ROOT / "scripts/wizard/operations.sh").read_text(encoding="utf-8")
        self.assertIn("Deployment versions and Flight Plan", guided)
        self.assertIn("Flight Plan:", guided)
        self.assertIn('section "Flight Plan"', guided)
        self.assertIn("flight_plan_show_comparison", operations)


if __name__ == "__main__":
    unittest.main()
