"""Contract tests for offline documentation quality gates."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationQualityGateTests(unittest.TestCase):
    def test_validator_passes_repository_documentation(self) -> None:
        result = subprocess.run(
            ["python3", "scripts/validate_docs.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ci_uses_single_local_entry_point(self) -> None:
        workflow = (ROOT / ".github/workflows/docs-quality.yml").read_text(encoding="utf-8")
        runner = (ROOT / "scripts/validate-docs.sh").read_text(encoding="utf-8")
        self.assertIn("./scripts/validate-docs.sh", workflow)
        self.assertIn("requirements-docs.txt", workflow)
        self.assertIn("python3 scripts/validate_docs.py", runner)
        self.assertIn("build --strict", runner)
        self.assertNotIn("microk8s", workflow.lower())
        self.assertNotIn("kubectl", workflow.lower())

    def test_validator_covers_required_gate_categories(self) -> None:
        source = (ROOT / "scripts/validate_docs.py").read_text(encoding="utf-8")
        expected = (
            "validate_links",
            "validate_nav",
            "validate_mermaid",
            "validate_wizard_topics",
            "validate_sensitive_content",
            "validate_shell",
            "TERMINOLOGY",
            "markdown_quality",
        )
        for gate in expected:
            with self.subTest(gate=gate):
                self.assertIn(gate, source)

    def test_pages_publish_is_main_only_and_least_privilege(self) -> None:
        workflow = (ROOT / ".github/workflows/docs-pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("branches: [main]", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("python -m mkdocs build --strict", workflow)
        for unsafe_command in ("microk8s", "kubectl", "start_wizard.sh"):
            self.assertNotIn(unsafe_command, workflow.lower())

    def test_publishing_guidance_records_site_and_private_repo_boundary(self) -> None:
        guidance = (ROOT / "docs/contributing/publishing.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("https://treisland.github.io/fortifylab/", guidance)
        self.assertIn("repository is private", guidance)
        self.assertIn("GitHub plan", guidance)
        self.assertIn("GitHub Actions", guidance)
        self.assertIn("./scripts/validate-docs.sh", guidance)
        self.assertIn("lab/demo", guidance.lower())


if __name__ == "__main__":
    unittest.main()
