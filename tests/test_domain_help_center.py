"""Unit tests for fortifylab.domain.help_center (M5 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.domain.help_center import HELP_TOPICS, default_help_dir, load_topic_text  # noqa: E402


class HelpCenterDomainTests(unittest.TestCase):
    def test_every_topic_file_exists_in_the_committed_docs_help_directory(self) -> None:
        help_dir = default_help_dir()
        for topic in HELP_TOPICS:
            self.assertTrue((help_dir / topic.filename).is_file(), f"missing docs/help/{topic.filename}")

    def test_load_topic_text_returns_real_committed_content(self) -> None:
        overview = next(topic for topic in HELP_TOPICS if topic.topic_id == "overview")
        text = load_topic_text(overview)
        self.assertIn("FORTIFY LAB", text.upper())

    def test_load_topic_text_raises_for_a_missing_file(self) -> None:
        from fortifylab.domain.help_center import HelpTopic

        missing = HelpTopic("nope", "Nonexistent", "does-not-exist.txt")
        with self.assertRaises(FileNotFoundError):
            load_topic_text(missing)

    def test_topic_ids_are_unique(self) -> None:
        ids = [topic.topic_id for topic in HELP_TOPICS]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
