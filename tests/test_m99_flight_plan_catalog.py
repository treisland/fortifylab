"""M9.9R Flight Plan catalog tests for the guided Python TUI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fortifylab.flight_plans import FlightPlanCatalogError, load_flight_plan_catalog


class FlightPlanCatalogTests(unittest.TestCase):
    def _write_base(self, directory: Path) -> Path:
        path = directory / "flight-plans.toml"
        path.write_text(
            """
schema_version = 1
default_flight_plan = "fortify-26.2"

[database_defaults]
FORTIFY_MYSQL_IMAGE_TAG = "8"

[flight_plans."fortify-26.2"]
label = "Fortify 26.2"
status = "recommended"
family = "26.2"
notes = "Repo baseline."

[flight_plans."fortify-26.2".components]
FORTIFY_SSC_IMAGE_TAG = "26.2.0"

[flight_plans."fortify-25.x"]
label = "Fortify 25.x"
status = "candidate"
family = "25"
notes = "Candidate."

[flight_plans."fortify-25.x".components]
FORTIFY_SSC_IMAGE_TAG = ""
""".strip()
            + "\n"
        )
        return path

    def test_loads_repo_catalog_with_default_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_base(Path(tmp))

            catalog = load_flight_plan_catalog(path)

        self.assertEqual(catalog.default_flight_plan, "fortify-26.2")
        self.assertEqual([plan.id for plan in catalog.flight_plans], ["fortify-26.2", "fortify-25.x"])
        self.assertEqual(catalog.by_id("fortify-26.2").components["FORTIFY_SSC_IMAGE_TAG"], "26.2.0")

    def test_local_catalog_adds_and_overrides_plans_without_replacing_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_base(Path(tmp))
            local = path.with_name("flight-plans.local.toml")
            local.write_text(
                """
[flight_plans."fortify-26.2"]
label = "Fortify 26.2 Local"
status = "known-good"
family = "26.2"
notes = "Local override."

[flight_plans."fortify-26.2".components]
FORTIFY_SSC_IMAGE_TAG = "26.2.1-local"

[flight_plans."fortify-27.1"]
label = "Fortify 27.1"
status = "candidate"
family = "27.1"
notes = "Local candidate."

[flight_plans."fortify-27.1".components]
FORTIFY_SSC_IMAGE_TAG = "27.1.0"
""".strip()
                + "\n"
            )

            catalog = load_flight_plan_catalog(path)

        self.assertEqual(catalog.default_flight_plan, "fortify-26.2")
        self.assertEqual(catalog.by_id("fortify-26.2").source, "local")
        self.assertEqual(catalog.by_id("fortify-26.2").components["FORTIFY_SSC_IMAGE_TAG"], "26.2.1-local")
        self.assertEqual(catalog.by_id("fortify-27.1").source, "local")

    def test_rejects_invalid_plan_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_base(Path(tmp))
            text = path.read_text().replace('status = "recommended"', 'status = "random"', 1)
            path.write_text(text)

            with self.assertRaises(FlightPlanCatalogError):
                load_flight_plan_catalog(path)


if __name__ == "__main__":
    unittest.main()
