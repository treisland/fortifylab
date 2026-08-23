"""Unit tests for ConfigurationScreen (M4 of the TUI migration)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.config.store import ConfigStore  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.configuration import ConfigurationScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


class ConfigurationScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.env_path = Path(self.tempdir.name) / ".env"
        self.env_path.write_text(
            "DOMAIN=fortifydemo.com\nDEFAULT_PASS=super-secret\nLIM_SIGNING_CERT_PWD=another-secret\n",
            encoding="utf-8",
        )
        self.store = ConfigStore(self.env_path)

    def _screen(self) -> ConfigurationScreen:
        return ConfigurationScreen(style=TerminalStyle(color=False, symbols=False), store=self.store)

    def test_renders_values_with_secret_shaped_keys_redacted(self) -> None:
        rendered = self._screen().render()
        self.assertIn("DOMAIN", rendered)
        self.assertIn("fortifydemo.com", rendered)
        self.assertIn("DEFAULT_PASS", rendered)
        self.assertNotIn("super-secret", rendered)
        self.assertIn("LIM_SIGNING_CERT_PWD", rendered)
        self.assertNotIn("another-secret", rendered)
        self.assertIn("<redacted>", rendered)

    def test_missing_env_file_shows_a_message_instead_of_crashing(self) -> None:
        missing = ConfigStore(Path(self.tempdir.name) / "does-not-exist.env")
        screen = ConfigurationScreen(style=TerminalStyle(color=False, symbols=False), store=missing)
        self.assertIn("does not exist yet", screen.render())

    def test_backup_does_not_require_arming(self) -> None:
        screen = self._screen()
        self.assertFalse(screen.armed)
        screen.handle_event(KeyEvent("b"))
        self.assertIn("Backup created", screen.last_message)
        self.assertEqual(len(self.store.backups()), 1)

    def test_rollback_requires_arming_first(self) -> None:
        screen = self._screen()
        screen.handle_event(KeyEvent("b"))  # have a backup to roll back to
        screen.handle_event(KeyEvent("r"))
        self.assertIn("Press a to arm", screen.last_message)
        self.assertFalse(screen.armed)

    def test_rollback_when_armed_restores_the_backup_and_auto_disarms(self) -> None:
        screen = self._screen()
        screen.handle_event(KeyEvent("b"))
        self.env_path.write_text("DOMAIN=changed.example.com\n", encoding="utf-8")
        screen.handle_event(KeyEvent("a"))
        self.assertTrue(screen.armed)
        screen.handle_event(KeyEvent("r"))
        self.assertIn("Rolled back", screen.last_message)
        self.assertFalse(screen.armed)
        self.assertIn("fortifydemo.com", self.env_path.read_text(encoding="utf-8"))

    def test_q_pops(self) -> None:
        command = self._screen().handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
