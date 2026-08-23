"""Unit tests for ApplicationsScreen (M4 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.operations import OperationCatalog, OperationRunner  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.applications import ApplicationsScreen  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _plain_screen() -> ApplicationsScreen:
    return ApplicationsScreen(style=TerminalStyle(color=False, symbols=False))


class ApplicationsScreenTests(unittest.TestCase):
    def test_renders_every_app_and_action(self) -> None:
        screen = _plain_screen()
        rendered = screen.render()
        self.assertIn("Software Security Center", rendered)
        self.assertIn("start", rendered)
        self.assertIn("stop", rendered)

    def test_includes_sample_apps_alongside_core_apps(self) -> None:
        # sample_apps_menu in Bash is a separate menu number from apps_menu,
        # but the underlying operation shape is identical, so this one
        # screen covers both rather than duplicating the same logic twice.
        screen = _plain_screen()
        rendered = screen.render()
        for label in ("Juice Shop (sample)", "WebGoat (sample)", "DVWA (sample)"):
            self.assertIn(label, rendered)

    def test_sample_app_rows_run_through_the_real_catalog(self) -> None:
        screen = _plain_screen()
        juice_shop_index = next(i for i, (app_id, _l, _a) in enumerate(screen.rows) if app_id == "juice-shop")
        screen.selected_index = juice_shop_index
        screen.handle_event(KeyEvent("enter"))
        self.assertIsNotNone(screen.last_execution)
        self.assertIn("juice-shop", screen.last_execution.operation_id)

    def test_no_row_offers_destroy(self) -> None:
        # Destroy needs a typed confirmation phrase; there's no text-entry
        # widget yet, so it must not appear as a selectable row.
        screen = _plain_screen()
        self.assertTrue(all(action != "destroy" for _app_id, _label, action in screen.rows))

    def test_starts_in_dry_run_mode(self) -> None:
        screen = _plain_screen()
        self.assertFalse(screen.armed)
        self.assertIn("dry-run", screen.render())

    def test_enter_in_dry_run_mode_previews_without_executing(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        self.assertIsNotNone(screen.last_execution)
        self.assertFalse(screen.last_execution.executed)

    def test_enter_when_armed_executes_and_auto_disarms(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_runner(command):
            calls.append(command)
            from fortifylab.core.command import CommandResult

            return CommandResult(args=command, returncode=0, stdout="started", stderr="", duration_seconds=0.0)

        screen = ApplicationsScreen(
            style=TerminalStyle(color=False, symbols=False),
            catalog=OperationCatalog(),
            runner=OperationRunner(fake_runner),
            armed=True,
        )
        screen.handle_event(KeyEvent("enter"))

        self.assertTrue(calls)
        self.assertTrue(screen.last_execution.executed)
        self.assertTrue(screen.last_execution.ok)
        self.assertFalse(screen.armed)

    def test_navigation_wraps(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("up"))
        self.assertEqual(screen.selected_index, len(screen.rows) - 1)

    def test_navigating_after_arming_disarms(self) -> None:
        # Arming is per-row, not session-wide: navigating to a different
        # row after arming must not leave a stale arm that fires against
        # whatever row the operator lands on next.
        screen = _plain_screen()
        screen.handle_event(KeyEvent("a"))
        self.assertTrue(screen.armed)

        screen.handle_event(KeyEvent("down"))

        self.assertFalse(screen.armed)

    def test_navigating_up_after_arming_also_disarms(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("a"))
        self.assertTrue(screen.armed)

        screen.handle_event(KeyEvent("up"))

        self.assertFalse(screen.armed)

    def test_q_pops(self) -> None:
        screen = _plain_screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
