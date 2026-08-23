"""Unit tests for DiagnosticsScreen (M5 of the TUI migration)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.diagnostics import ClusterCollector  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.diagnostics import DiagnosticsScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _collector(*, all_ok: bool) -> ClusterCollector:
    def fake_runner(command: tuple[str, ...]) -> CommandResult:
        return CommandResult(args=command, returncode=0 if all_ok else 1, stdout="ok\n", stderr="", duration_seconds=0.0)

    return ClusterCollector(runner=fake_runner)


class DiagnosticsScreenTests(unittest.TestCase):
    def test_no_results_before_first_collection(self) -> None:
        screen = DiagnosticsScreen(style=TerminalStyle(color=False, symbols=False))
        self.assertIn("No collection run yet", screen.render())

    def test_enter_collects_and_shows_ok_results(self) -> None:
        screen = DiagnosticsScreen(style=TerminalStyle(color=False, symbols=False), collector=_collector(all_ok=True))
        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(screen.results)
        self.assertTrue(all(result.ok for result in screen.results))

    def test_r_also_collects(self) -> None:
        screen = DiagnosticsScreen(style=TerminalStyle(color=False, symbols=False), collector=_collector(all_ok=False))
        screen.handle_event(KeyEvent("r"))
        self.assertTrue(screen.results)
        self.assertFalse(any(result.ok for result in screen.results))

    def test_bundle_requires_a_collection_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = DiagnosticsScreen(
                style=TerminalStyle(color=False, symbols=False),
                bundle_dir=Path(directory) / "diagnostics",
            )
            screen.handle_event(KeyEvent("b"))
            self.assertIn("Run a collection first", screen.message)

    def test_bundle_writes_a_sanitized_archive_after_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle_dir = Path(directory) / "diagnostics"
            screen = DiagnosticsScreen(
                style=TerminalStyle(color=False, symbols=False),
                collector=_collector(all_ok=True),
                bundle_dir=bundle_dir,
            )
            screen.handle_event(KeyEvent("enter"))
            screen.handle_event(KeyEvent("b"))
            self.assertIn("Diagnostics bundle written", screen.message)
            self.assertTrue((bundle_dir / "fortifylab-diagnostics.tar.gz").exists())

    def test_q_pops(self) -> None:
        screen = DiagnosticsScreen(style=TerminalStyle(color=False, symbols=False))
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
