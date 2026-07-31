"""Contracts for the authoritative documentation architecture decision."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs/adr/0001-mkdocs-authoritative-documentation.md"
ADR_INDEX = ROOT / "docs/adr/README.md"


class DocumentationArchitectureTests(unittest.TestCase):
    def test_adr_is_indexed_and_accepted(self) -> None:
        self.assertTrue(ADR.is_file())
        self.assertIn(ADR.name, ADR_INDEX.read_text(encoding="utf-8"))
        self.assertIn("Status: Accepted", ADR.read_text(encoding="utf-8"))

    def test_source_boundaries_and_topic_contract_are_recorded(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for contract in (
            "`docs/` is authoritative",
            "`README.md` is the concise repository entry point",
            "`docs/help/` remains committed",
            "stable, path-like topic IDs",
            "GitHub Wiki, if enabled, is informal only",
        ):
            self.assertIn(contract, text)

    def test_delivery_flows_and_private_pages_constraints_are_recorded(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for heading in ("### Local", "### Pull request and CI", "### Published"):
            self.assertIn(heading, text)
        self.assertIn("repository was verified as **private**", text)
        self.assertIn("access-controlled private publication", text)
        self.assertIn("choose the intended site visibility explicitly", text)

    def test_lab_and_secret_safety_boundaries_are_recorded(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("lab/demo-only boundary", text)
        self.assertIn("synthetic data", text)
        self.assertIn("must never copy", text)
        self.assertIn("licenses", text)
        self.assertIn("tokens", text)


if __name__ == "__main__":
    unittest.main()
