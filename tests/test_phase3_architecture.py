"""Contracts for the Phase 3 Python migration architecture."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "0002-python-runtime-migration.md"
GUIDE = ROOT / "docs" / "development" / "phase-3-python-migration.md"


class Phase3ArchitectureTests(unittest.TestCase):
    def test_python_runtime_decision_is_recorded_and_indexed(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        index = (ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
        nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertIn("Status: Accepted", text)
        self.assertIn("migrate its application runtime to Python", text)
        self.assertIn("clone-and-run", text)
        self.assertIn("0002-python-runtime-migration.md", index)
        self.assertIn("ADR 0002: Python runtime migration", nav)

    def test_bash_compatibility_and_replacement_policy_is_explicit(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for phrase in (
            "`start_wizard.sh` remains a supported compatibility entrypoint",
            "compatibility launchers",
            "Bash script can become a wrapper",
            "Removing a Bash entrypoint requires",
        ):
            self.assertIn(phrase, text)

    def test_hybrid_state_model_keeps_cluster_authoritative(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for phrase in (
            "Live Kubernetes, Helm, and host state remain authoritative",
            "selected deployment profile",
            "current or last failed guided step",
            "must not store credentials",
            "raw application logs",
        ):
            self.assertIn(phrase, text)

    def test_phase3_integration_runway_avoids_dev_and_main_until_manual_acceptance(self) -> None:
        text = ADR.read_text(encoding="utf-8") + GUIDE.read_text(encoding="utf-8")
        for phrase in (
            "agent/phase-3.7-3.10-python-cli-tui",
            "Phase 3.0-3.6",
            "customer demo",
            "workshop/classroom",
            "dev",
            "main",
            "manual validation",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("integration/cli-phases-2.7-3.6", text)

    def test_phase3_migration_guide_is_in_docs_navigation(self) -> None:
        nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        guide = GUIDE.read_text(encoding="utf-8")
        self.assertIn("Phase 3 Python migration: development/phase-3-python-migration.md", nav)
        self.assertIn("guided deployment profile selection", guide)
        self.assertIn("CLI/TUI-first operator", guide)
        self.assertIn("Fortify Lab management is out of scope", guide)
        self.assertIn("Phase 3.7 direction reset", guide)
        self.assertIn("Phase 3.8 dependency foundation", guide)

    def test_python_dependency_policy_is_documented_without_web_ui_scope(self) -> None:
        text = ADR.read_text(encoding="utf-8") + GUIDE.read_text(encoding="utf-8")
        for phrase in (
            "Typer",
            "Rich",
            "Textual",
            "Pydantic",
            "requirements-python.txt",
            "standard library",
            "does not introduce a Fortify Lab web UI",
            "Bash remains the production guided wizard",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
