"""Unit tests for UrlsCredentialsScreen (#446 slice 4)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.urls_credentials_service import UrlsCredentialsService  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.urls_credentials import UrlsCredentialsScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _screen(*, env_text: str | None = None, env_dir: Path | None = None) -> UrlsCredentialsScreen:
    service = UrlsCredentialsService(runner=lambda args: CommandResult(args, 0, "present", "", 0.0))
    kwargs = {"style": TerminalStyle(color=False, symbols=False), "service": service}
    if env_dir is not None:
        env_path = env_dir / ".env"
        if env_text is not None:
            env_path.write_text(env_text, encoding="utf-8")
        kwargs["env_file"] = env_path
    return UrlsCredentialsScreen(**kwargs)


class UrlsCredentialsScreenTests(unittest.TestCase):
    def test_renders_service_urls_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(
                env_text="SSC_URL=https://ssc.example.com\nDOMAIN=example.com\n",
                env_dir=Path(directory),
            )
            rendered = screen.render()
            self.assertIn("https://ssc.example.com", rendered)
            self.assertIn("https://dashboard.example.com", rendered)

    def test_missing_env_file_shows_unset_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(env_dir=Path(directory))
            self.assertIn("<unset>", screen.render())

    def test_renders_static_login_guidance(self) -> None:
        rendered = _screen().render()
        self.assertIn("admin / refer to the SSC documentation", rendered)
        self.assertIn("lim_admin", rendered)

    def test_no_availability_check_before_c_is_pressed(self) -> None:
        screen = _screen()
        self.assertIsNone(screen.availability)
        self.assertIn("press c to check", screen.render())

    def test_c_runs_the_availability_check(self) -> None:
        screen = _screen()
        screen.handle_event(KeyEvent("c"))
        self.assertIsNotNone(screen.availability)
        self.assertIn("available", screen.render())

    def test_never_renders_an_actual_secret_value(self) -> None:
        # The service only ever returns booleans; even a "present" result
        # must not leak the raw stdout used to determine that.
        screen = _screen()
        screen.handle_event(KeyEvent("c"))
        rendered = screen.render()
        self.assertNotIn("c29tZS12YWx1ZQ==", rendered)

    def test_unavailable_credential_is_colored_warn_not_muted(self) -> None:
        # Regression test: Bash's credential_present_label() colors a
        # missing credential yellow ($YELLOW/warn), not dim -- it's a real
        # "not there yet" signal, not inert text. Use a color-enabled
        # style (the real runtime default) and check for the raw ANSI
        # warn code (33), not the muted code (2).
        service = UrlsCredentialsService(runner=lambda args: CommandResult(args, 1, "", "not found", 0.0))
        screen = UrlsCredentialsScreen(style=TerminalStyle(color=True, symbols=True), service=service)
        screen.handle_event(KeyEvent("c"))
        rendered = screen.render()
        self.assertIn("[33m", rendered)

    def test_q_pops(self) -> None:
        screen = _screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
