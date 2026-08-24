"""M4: main menu 'o' wiring for the applications/configuration/logs screens."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.applications import ApplicationsScreen  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.certificates import CertificatesScreen  # noqa: E402
from fortifylab.tui.screens.configuration import ConfigurationScreen  # noqa: E402
from fortifylab.tui.screens.dashboard import DashboardScreen  # noqa: E402
from fortifylab.tui.screens.dashboard_access import DashboardAccessScreen  # noqa: E402
from fortifylab.tui.screens.diagnostics import DiagnosticsScreen  # noqa: E402
from fortifylab.tui.screens.flight_plans import FlightPlansScreen  # noqa: E402
from fortifylab.tui.screens.help import HelpScreen  # noqa: E402
from fortifylab.tui.screens.logs import LogsScreen  # noqa: E402
from fortifylab.tui.screens.main_menu import MainMenuScreen  # noqa: E402
from fortifylab.tui.screens.runbooks import RunbooksScreen  # noqa: E402
from fortifylab.tui.screens.urls_credentials import UrlsCredentialsScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


class MainMenuOpensM4ScreensTests(unittest.TestCase):
    def _push_via_o(self, item_key: str):
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        index = next(i for i, item in enumerate(menu.items) if item.key == item_key)
        menu.selected_index = index
        return menu.handle_event(KeyEvent("o"))

    def test_o_on_applications_opens_applications_screen(self) -> None:
        command = self._push_via_o("applications")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, ApplicationsScreen)

    def test_o_on_configuration_opens_configuration_screen(self) -> None:
        command = self._push_via_o("configuration")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, ConfigurationScreen)

    def test_o_on_logs_opens_logs_screen(self) -> None:
        command = self._push_via_o("logs")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, LogsScreen)

    def test_o_on_diagnostics_opens_diagnostics_screen(self) -> None:
        command = self._push_via_o("diagnostics")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, DiagnosticsScreen)

    def test_o_on_runbooks_opens_runbooks_screen(self) -> None:
        command = self._push_via_o("runbooks")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, RunbooksScreen)

    def test_o_on_help_opens_help_screen(self) -> None:
        command = self._push_via_o("help")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, HelpScreen)

    def test_o_on_tools_opens_flight_plans_screen(self) -> None:
        command = self._push_via_o("tools")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, FlightPlansScreen)

    def test_o_on_kubernetes_dashboard_opens_dashboard_access_screen(self) -> None:
        command = self._push_via_o("kubernetes-dashboard")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, DashboardAccessScreen)

    def test_o_on_urls_credentials_opens_urls_credentials_screen(self) -> None:
        command = self._push_via_o("urls-credentials")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, UrlsCredentialsScreen)

    def test_o_on_certificates_opens_certificates_screen(self) -> None:
        command = self._push_via_o("certificates")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, CertificatesScreen)

    def test_o_on_dashboard_opens_dashboard_screen(self) -> None:
        command = self._push_via_o("dashboard")
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, DashboardScreen)

    def test_preview_hints_at_opening_for_all_wired_items(self) -> None:
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        for key in (
            "dashboard",
            "deploy",
            "applications",
            "configuration",
            "logs",
            "diagnostics",
            "runbooks",
            "help",
            "tools",
            "kubernetes-dashboard",
            "urls-credentials",
            "certificates",
        ):
            index = next(i for i, item in enumerate(menu.items) if item.key == key)
            menu.selected_index = index
            menu.show_detail = True
            self.assertIn("press o to open", menu.render())


if __name__ == "__main__":
    unittest.main()
