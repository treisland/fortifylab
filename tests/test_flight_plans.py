"""Contracts for Fortify Flight Plans catalog, discovery, and wizard integration."""

from __future__ import annotations

import json
import os
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
        self.assertIn("Wrote candidate Flight Plan draft", result.stdout)

    def test_discovery_reuses_catalog_values_when_repo_listing_is_unavailable(self) -> None:
        payload = {"results": [{"name": "26.2.0-1"}], "next": None}
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory) / "fixtures"
            fixture_dir.mkdir()
            for repo in (
                "fortifydocker__helm-ssc__page1.json",
                "fortifydocker__helm-scancentral-sast__page1.json",
                "fortifydocker__helm-scancentral-dast-core__page1.json",
                "fortifydocker__helm-lim__page1.json",
            ):
                (fixture_dir / repo).write_text(json.dumps(payload), encoding="utf-8")
            output = Path(directory) / "candidate.toml"
            result = self.run_tool("discover", "--family", "26.2", "--fixture-dir", str(fixture_dir), "--output", str(output))
            candidate = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FORTIFY_SSC_IMAGE_TAG = "26.2.0.0183"', candidate)
        self.assertIn('FORTIFY_SCSAST_CTRL_IMAGE_TAG = "26.2.0"', candidate)
        self.assertIn('FORTIFY_SCSAST_WORKER_IMAGE_TAG = "25.2.0"', candidate)
        self.assertIn("reused catalog value", result.stdout)
        self.assertNotIn("FORTIFY_SSC_IMAGE_TAG: FORTIFY_SSC_IMAGE_TAG", result.stdout)

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
