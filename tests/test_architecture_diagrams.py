"""Contracts for accessible, implementation-aligned architecture diagrams."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = ROOT / "docs" / "fortify" / "architecture-and-flows.md"


class ArchitectureDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = DIAGRAMS.read_text(encoding="utf-8")

    def test_required_diagrams_are_present(self) -> None:
        for heading in (
            "## Lab topology",
            "## Enforced startup dependencies",
            "## Deployment order",
            "## Static analysis flow",
            "## Dynamic analysis flow",
            "## Secret material flow",
            "## Recovery order",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.content)

    def test_every_mermaid_diagram_has_a_text_alternative(self) -> None:
        diagrams = re.findall(
            r"```mermaid\n.*?\n```\n\n(?P<alternative>[^\n]+)",
            self.content,
            flags=re.DOTALL,
        )
        self.assertEqual(7, len(diagrams))
        self.assertTrue(
            all(item.startswith("**Text alternative.**") for item in diagrams)
        )

    def test_dependency_resource_names_match_the_health_contract(self) -> None:
        health = (ROOT / "scripts" / "lib" / "dependency-health.sh").read_text(
            encoding="utf-8"
        )
        for resource in (
            "mysql",
            "postgresql",
            "ssc-webapp",
            "lim",
            "sdast-core-scancentral-dast-core-api",
            "sdast-core-scancentral-dast-core-globalservice",
            "sdast-core-scancentral-dast-core-utilityservice",
        ):
            with self.subTest(resource=resource):
                self.assertIn(resource, health)
                self.assertIn(resource, self.content)

    def test_diagrams_are_in_site_navigation(self) -> None:
        config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertIn("fortify/architecture-and-flows.md", config)


if __name__ == "__main__":
    unittest.main()
