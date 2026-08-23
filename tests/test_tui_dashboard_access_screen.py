"""Unit tests for DashboardAccessScreen (#446 slice 3)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.dashboard_access_service import DashboardAccessService  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.dashboard_access import DashboardAccessScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _ready_service(*, token: str = "fake-token") -> DashboardAccessService:
    return DashboardAccessService(runner=lambda args: CommandResult(args, 0, token, "", 0.0))


def _not_ready_service() -> DashboardAccessService:
    def runner(args: tuple[str, ...]) -> CommandResult:
        if "get" in args:
            return CommandResult(args, 1, "", "not found", 0.0)
        return CommandResult(args, 0, "token", "", 0.0)

    return DashboardAccessService(runner=runner)


def _screen(service: DashboardAccessService, *, armed: bool = False) -> DashboardAccessScreen:
    return DashboardAccessScreen(style=TerminalStyle(color=False, symbols=False), service=service, armed=armed)


class DashboardAccessScreenTests(unittest.TestCase):
    def test_starts_not_armed_and_shows_the_admin_warning(self) -> None:
        screen = _screen(_ready_service())
        rendered = screen.render()
        self.assertIn("not armed", rendered)
        self.assertIn("WARNING", rendered)

    def test_v_generates_a_viewer_token_without_arming(self) -> None:
        screen = _screen(_ready_service(token="viewer-jwt"))
        screen.handle_event(KeyEvent("v"))
        self.assertIn("view-only", screen.message.lower())
        self.assertIn("viewer-jwt", screen.message)

    def test_m_without_arming_refuses_and_prompts_to_arm(self) -> None:
        screen = _screen(_ready_service())
        screen.handle_event(KeyEvent("m"))
        self.assertIn("Press a to arm", screen.message)

    def test_m_when_armed_generates_an_admin_token_and_auto_disarms(self) -> None:
        screen = _screen(_ready_service(token="admin-jwt"), armed=True)
        screen.handle_event(KeyEvent("m"))
        self.assertIn("administrator", screen.message.lower())
        self.assertIn("admin-jwt", screen.message)
        self.assertFalse(screen.armed)

    def test_v_disarms_a_stale_arm_intended_for_m(self) -> None:
        # An arm meant for the admin token must not silently survive an
        # unrelated viewer-token action and carry over to a later "m".
        screen = _screen(_ready_service(), armed=True)
        screen.handle_event(KeyEvent("v"))
        self.assertFalse(screen.armed)

    def test_missing_resources_shows_an_error_instead_of_generating(self) -> None:
        screen = _screen(_not_ready_service())
        screen.handle_event(KeyEvent("v"))
        self.assertIn("missing or incomplete", screen.message)

    def test_failed_token_creation_shows_the_command_error(self) -> None:
        def runner(args: tuple[str, ...]) -> CommandResult:
            if "create" in args:
                return CommandResult(args, 1, "", "permission denied", 0.0)
            return CommandResult(args, 0, "", "", 0.0)

        screen = _screen(DashboardAccessService(runner=runner))
        screen.handle_event(KeyEvent("v"))
        self.assertIn("permission denied", screen.message)

    def test_url_reflects_domain_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("DOMAIN=fortifydemo.com\n", encoding="utf-8")
            screen = DashboardAccessScreen(
                style=TerminalStyle(color=False, symbols=False),
                service=_ready_service(),
                env_file=env_path,
            )
            self.assertIn("https://dashboard.fortifydemo.com", screen.render())

    def test_missing_env_file_shows_unset_domain_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = DashboardAccessScreen(
                style=TerminalStyle(color=False, symbols=False),
                service=_ready_service(),
                env_file=Path(directory) / "does-not-exist.env",
            )
            self.assertIn("<unset>", screen.render())

    def test_q_pops(self) -> None:
        screen = _screen(_ready_service())
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
