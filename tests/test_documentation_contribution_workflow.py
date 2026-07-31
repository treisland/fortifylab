"""Contract tests for the sustainable documentation contribution workflow."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUIDE = (ROOT / "docs" / "contributing" / "index.md").read_text(encoding="utf-8")
GUIDE_PROSE = " ".join(GUIDE.split())


class DocumentationContributionWorkflowTests(unittest.TestCase):
    def test_authority_and_behavior_coupling_are_explicit(self) -> None:
        for expected in (
            "MkDocs content under `docs/` is authoritative",
            "A GitHub Wiki, if enabled, is informal only",
            "A behavior change is incomplete",
            "documentation and tests in that pull request",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, GUIDE_PROSE)

    def test_local_workflow_uses_the_ci_entry_point(self) -> None:
        self.assertIn(".venv/bin/mkdocs serve", GUIDE)
        self.assertGreaterEqual(GUIDE.count("./scripts/validate-docs.sh"), 2)
        workflow = (ROOT / ".github" / "workflows" / "docs-quality.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run: ./scripts/validate-docs.sh", workflow)

    def test_maintenance_contract_covers_required_topics(self) -> None:
        for expected in (
            "## Add or move a page",
            "### Preserve routes and redirects",
            "## Maintain wizard help mappings",
            "HELP_TOPIC_ID",
            "## Write diagrams",
            "```mermaid",
            "## Use consistent terminology and version claims",
            "## Sanitize screenshots and examples",
            "## Review expectations",
            "## Contributor checklist",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, GUIDE)

    def test_screenshot_rules_require_real_sanitization_and_review(self) -> None:
        for expected in (
            "replace the pixels",
            "remove metadata",
            "full resolution",
            "A second reviewer",
            "local images are rejected by default",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, GUIDE)


if __name__ == "__main__":
    unittest.main()
