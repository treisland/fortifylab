"""Contracts for the audience-oriented documentation information architecture."""

from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class DocumentationInformationArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.help_script = (ROOT / "scripts/lib/help.sh").read_text(
            encoding="utf-8"
        )

    def test_required_sections_are_in_navigation(self) -> None:
        for section in (
            "Getting started",
            "Fortify system",
            "Deployment",
            "Operations",
            "Configuration",
            "Troubleshooting",
            "Safety",
            "Contributing",
            "Architecture decisions",
        ):
            with self.subTest(section=section):
                self.assertIn(f"  - {section}:", self.config)

    def test_section_landing_pages_exist(self) -> None:
        for directory in (
            "getting-started",
            "fortify",
            "deployment",
            "operations",
            "configuration",
            "troubleshooting",
            "safety",
            "contributing",
            "adr",
        ):
            with self.subTest(directory=directory):
                filename = "README.md" if directory in {"operations", "adr"} else "index.md"
                self.assertTrue((DOCS / directory / filename).is_file())

    def test_released_documentation_paths_remain_compatible(self) -> None:
        for relative_path in (
            "lab-use.md",
            "help/README.md",
            "operations/deployment-and-lifecycle.md",
            "operations/networking-and-tls.md",
            "operations/troubleshooting.md",
            "operations/secrets-and-licenses.md",
            "operations/diagnostics.md",
            "operations/backup-and-recovery.md",
            "operations/versions-and-compatibility.md",
            "operations/first-scan.md",
        ):
            with self.subTest(relative_path=relative_path):
                self.assertTrue((DOCS / relative_path).is_file())

    def test_every_offline_help_topic_still_maps_to_a_readable_file(self) -> None:
        match = re.search(
            r"HELP_TOPIC_FILE=\(\n(?P<files>.*?)\n\)",
            self.help_script,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        files = re.findall(r"[A-Za-z0-9-]+\.txt", match.group("files"))
        self.assertGreater(len(files), 0)
        for filename in files:
            with self.subTest(filename=filename):
                self.assertTrue((DOCS / "help" / filename).is_file())


if __name__ == "__main__":
    unittest.main()
