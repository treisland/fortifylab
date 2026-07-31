"""Contracts for the beginner-facing Fortify Knowledge Center."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORTIFY = ROOT / "docs" / "fortify"


class KnowledgeCenterTests(unittest.TestCase):
    COMPONENTS = (
        "ssc.md",
        "scancentral-sast.md",
        "scancentral-dast.md",
        "lim.md",
        "mysql.md",
        "postgresql.md",
        "kubernetes-dashboard.md",
    )

    def test_every_component_has_the_learning_contract(self) -> None:
        headings = (
            "## Purpose and users",
            "## Data and interfaces",
            "## Dependencies",
            "## Failure symptoms",
            "## Stop impact",
        )
        for filename in self.COMPONENTS:
            content = (FORTIFY / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                for heading in headings:
                    self.assertIn(heading, content)
                self.assertIn("**Scan role:**", content)

    def test_overview_preserves_system_boundaries_and_dependency_paths(self) -> None:
        overview = (FORTIFY / "index.md").read_text(encoding="utf-8")
        normalized_overview = " ".join(overview.split())
        for statement in (
            "application-security system of record",
            "MySQL → SSC → ScanCentral SAST",
            "PostgreSQL and LIM → ScanCentral DAST",
            "Kubernetes Dashboard",
            "not a Fortify product",
            "Lab and demo use only",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, normalized_overview)

    def test_every_component_is_in_site_navigation(self) -> None:
        config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        for filename in self.COMPONENTS:
            with self.subTest(filename=filename):
                self.assertIn(f"fortify/{filename}", config)


if __name__ == "__main__":
    unittest.main()
