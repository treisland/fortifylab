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


if __name__ == "__main__":
    unittest.main()
