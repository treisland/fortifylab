"""Contract tests for the MkDocs documentation scaffold."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.requirements = (ROOT / "requirements-docs.txt").read_text(
            encoding="utf-8"
        )

    def test_site_sources_are_confined_to_committed_docs(self) -> None:
        self.assertIn("docs_dir: docs", self.config)
        self.assertIn("site_dir: site", self.config)
        self.assertNotIn("docs_dir: .", self.config)
        for unsafe_path in ("secrets/", "certs/"):
            self.assertNotIn(unsafe_path, self.config)

    def test_runtime_and_generated_secret_patterns_are_excluded(self) -> None:
        expected_exclusions = (
            "**/.env",
            "**/generated/**",
            "**/input/**",
            "**/*.key",
            "**/*.pem",
            "**/*.p12",
            "**/*.pfx",
            "**/*.jks",
            "**/*.license",
        )
        for pattern in expected_exclusions:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, self.config)

    def test_output_and_virtual_environments_are_ignored(self) -> None:
        for ignored in ("site/", ".venv/", "venv/"):
            self.assertIn(ignored, self.ignore)

    def test_documentation_dependencies_use_exact_pins(self) -> None:
        dependencies = [
            line
            for line in self.requirements.splitlines()
            if line and not line.startswith("#")
        ]
        self.assertGreaterEqual(len(dependencies), 2)
        for dependency in dependencies:
            self.assertRegex(dependency, r"^[A-Za-z0-9_.-]+==[^=\s]+$")

    def test_requested_material_features_are_configured(self) -> None:
        expected = (
            "name: material",
            "- search",
            "content.code.copy",
            "pymdownx.superfences",
            "name: mermaid",
            "- admonition",
            "pymdownx.tabbed",
            "scheme: default",
            "scheme: slate",
            "repo_url:",
            "edit_uri:",
            "strict: true",
        )
        for setting in expected:
            with self.subTest(setting=setting):
                self.assertIn(setting, self.config)


if __name__ == "__main__":
    unittest.main()
