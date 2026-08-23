"""Unit tests for the Python Flight Plan domain model (M1 of the TUI migration)."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.domain.flight_plans import (  # noqa: E402
    Catalog,
    default_catalog_path,
    load_catalog,
    load_local_catalog,
    local_catalog_path,
    merged_read_catalog,
    validate_catalog,
)
from fortifylab.services.flight_plan_service import FlightPlanService, parse_env_file, version_sort_key  # noqa: E402


class FlightPlanDomainTests(unittest.TestCase):
    def test_loads_the_real_repo_catalog_without_issues(self) -> None:
        catalog = load_catalog(default_catalog_path())
        issues = validate_catalog(catalog)
        self.assertEqual(issues, [])

    def test_repo_catalog_has_exactly_one_recommended_plan(self) -> None:
        catalog = load_catalog(default_catalog_path())
        recommended = [plan for plan in catalog.flight_plans.values() if plan.status == "recommended"]
        self.assertEqual(len(recommended), 1)
        self.assertEqual(recommended[0].plan_id, catalog.default_flight_plan)

    def test_candidate_plan_flags_missing_components_for_review(self) -> None:
        catalog = load_catalog(default_catalog_path())
        candidates = [plan for plan in catalog.flight_plans.values() if plan.is_candidate]
        self.assertTrue(candidates, "expected at least one candidate Flight Plan in the repo catalog")
        candidate = candidates[0]
        self.assertTrue(candidate.review_required_keys)

    def test_local_catalog_overlays_without_touching_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_path = Path(directory) / "flight-plans.toml"
            base_path.write_text(
                textwrap.dedent(
                    """
                    schema_version = 1
                    default_flight_plan = "base-plan"

                    [database_defaults]
                    FORTIFY_MYSQL_CHART_VERSION = "1"
                    FORTIFY_MYSQL_IMAGE_TAG = "1"
                    FORTIFY_POSTGRES_CHART_VERSION = "1"
                    FORTIFY_POSTGRES_IMAGE_TAG = "1"

                    [flight_plans."base-plan"]
                    label = "Base"
                    status = "recommended"
                    family = "1"
                    notes = ""

                    [flight_plans."base-plan".components]
                    FORTIFY_SSC_CHART_VERSION = "1"
                    FORTIFY_SSC_IMAGE_TAG = "1"
                    FORTIFY_SCSAST_CHART_VERSION = "1"
                    FORTIFY_SCSAST_CTRL_IMAGE_TAG = "1"
                    FORTIFY_SCSAST_WORKER_IMAGE_TAG = "1"
                    FORTIFY_SCDAST_CHART_VERSION = "1"
                    FORTIFY_LIM_CHART_VERSION = "1"
                    """
                ),
                encoding="utf-8",
            )
            local_path = local_catalog_path(base_path)
            local_path.write_text(
                textwrap.dedent(
                    """
                    schema_version = 1

                    [flight_plans."local-plan"]
                    label = "Local"
                    status = "candidate"
                    family = "local"
                    notes = ""

                    [flight_plans."local-plan".components]
                    """
                ),
                encoding="utf-8",
            )

            merged = merged_read_catalog(base_path)
            self.assertIn("base-plan", merged.flight_plans)
            self.assertIn("local-plan", merged.flight_plans)

            base_only = load_catalog(base_path)
            self.assertNotIn("local-plan", base_only.flight_plans)

    def test_missing_local_catalog_yields_empty_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_path = Path(directory) / "flight-plans.toml"
            base_path.write_text("schema_version = 1\n\n[flight_plans]\n", encoding="utf-8")
            local = load_local_catalog(base_path)
            self.assertEqual(local.flight_plans, {})


class ParseEnvFileSecurityTests(unittest.TestCase):
    def test_never_returns_keys_outside_the_allowlist_even_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                textwrap.dedent(
                    """
                    FORTIFY_SSC_CHART_VERSION=26.2.0-1
                    DEFAULT_PASS=super-secret
                    FORTIFY_LICENSE_FILE=/secrets/input/fortify.license
                    SSC_ADMIN_TOKEN=abc123
                    """
                ),
                encoding="utf-8",
            )
            values = parse_env_file(env_path)
            self.assertEqual(values, {"FORTIFY_SSC_CHART_VERSION": "26.2.0-1"})
            self.assertNotIn("DEFAULT_PASS", values)
            self.assertNotIn("FORTIFY_LICENSE_FILE", values)
            self.assertNotIn("SSC_ADMIN_TOKEN", values)

    def test_caller_must_opt_in_explicitly_to_read_other_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("DOMAIN=fortifydemo.com\n", encoding="utf-8")
            self.assertEqual(parse_env_file(env_path), {})
            self.assertEqual(parse_env_file(env_path, allowed_keys=("DOMAIN",)), {"DOMAIN": "fortifydemo.com"})


class VersionSortKeyTests(unittest.TestCase):
    def test_numeric_runs_sort_numerically_not_lexically(self) -> None:
        tags = ["26.9.0", "26.10.0", "26.2.0"]
        self.assertEqual(
            sorted(tags, key=version_sort_key),
            ["26.2.0", "26.9.0", "26.10.0"],
        )


class FlightPlanServiceTests(unittest.TestCase):
    def test_compare_env_flags_drift_and_review_required_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "flight-plans.toml"
            catalog_path.write_text(
                textwrap.dedent(
                    """
                    schema_version = 1
                    default_flight_plan = "test-plan"

                    [database_defaults]
                    FORTIFY_MYSQL_CHART_VERSION = "9.0.0"
                    FORTIFY_MYSQL_IMAGE_TAG = "8.0.0"
                    FORTIFY_POSTGRES_CHART_VERSION = "18.0.0"
                    FORTIFY_POSTGRES_IMAGE_TAG = "17.0.0"

                    [flight_plans."test-plan"]
                    label = "Test"
                    status = "recommended"
                    family = "test"
                    notes = ""

                    [flight_plans."test-plan".components]
                    FORTIFY_SSC_CHART_VERSION = "26.2.0-1"
                    FORTIFY_SSC_IMAGE_TAG = ""
                    FORTIFY_SCSAST_CHART_VERSION = "26.2.0-1"
                    FORTIFY_SCSAST_CTRL_IMAGE_TAG = "26.2.0"
                    FORTIFY_SCSAST_WORKER_IMAGE_TAG = "25.2.0"
                    FORTIFY_SCDAST_CHART_VERSION = "24.4.0-2"
                    FORTIFY_LIM_CHART_VERSION = "24.4.0-3"
                    """
                ),
                encoding="utf-8",
            )
            env_path = Path(directory) / ".env"
            env_path.write_text(
                'FORTIFY_SSC_CHART_VERSION="25.1.0-1"\nFORTIFY_SCSAST_CHART_VERSION=26.2.0-1\n',
                encoding="utf-8",
            )

            service = FlightPlanService(load_catalog(catalog_path))
            comparison = service.compare_env("test-plan", env_path)

            drifted_keys = {field.key for field in comparison.mismatched}
            self.assertIn("FORTIFY_SSC_CHART_VERSION", drifted_keys)
            self.assertNotIn("FORTIFY_SCSAST_CHART_VERSION", drifted_keys)
            # An empty expected value means "review required", not "drifted".
            self.assertNotIn("FORTIFY_SSC_IMAGE_TAG", drifted_keys)
            self.assertTrue(comparison.drifted)


if __name__ == "__main__":
    unittest.main()
