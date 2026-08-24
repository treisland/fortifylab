"""Unit tests for DashboardScreen (#446 slice 6)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.services.lab_status_service import ReadinessCheck  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.dashboard import DashboardScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


class _FakeService:
    def __init__(self, checks: tuple[ReadinessCheck, ...]) -> None:
        self._checks = checks
        self.calls = 0

    def readiness(self) -> tuple[ReadinessCheck, ...]:
        self.calls += 1
        return self._checks


def _screen(checks: tuple[ReadinessCheck, ...]) -> tuple[DashboardScreen, _FakeService]:
    service = _FakeService(checks)
    screen = DashboardScreen(style=TerminalStyle(color=False, symbols=False), service=service)
    return screen, service


class DashboardScreenTests(unittest.TestCase):
    def test_runs_checks_on_construction(self) -> None:
        _, service = _screen((ReadinessCheck("thing", True),))
        self.assertEqual(service.calls, 1)

    def test_renders_score_and_each_check_label(self) -> None:
        screen, _ = _screen(
            (
                ReadinessCheck(".env file exists", True),
                ReadinessCheck("Kubernetes cluster is reachable", False, "start MicroK8s or check kube context"),
            )
        )
        rendered = screen.render()
        self.assertIn("1/2", rendered)
        self.assertIn(".env file exists", rendered)
        self.assertIn("Kubernetes cluster is reachable", rendered)
        self.assertIn("start MicroK8s or check kube context", rendered)

    def test_recommended_next_action_is_first_warn_detail(self) -> None:
        screen, _ = _screen(
            (
                ReadinessCheck("a", False, "fix a first"),
                ReadinessCheck("b", False, "fix b second"),
            )
        )
        rendered = screen.render()
        self.assertIn("Recommended next action: fix a first", rendered)
        self.assertNotIn("Recommended next action: fix b second", rendered)

    def test_recommended_next_action_when_everything_ready(self) -> None:
        screen, _ = _screen((ReadinessCheck("a", True), ReadinessCheck("b", True)))
        rendered = screen.render()
        self.assertIn("Recommended next action: none", rendered)

    def test_r_reruns_checks(self) -> None:
        screen, service = _screen((ReadinessCheck("a", True),))
        screen.handle_event(KeyEvent("r"))
        self.assertEqual(service.calls, 2)

    def test_q_pops(self) -> None:
        screen, _ = _screen((ReadinessCheck("a", True),))
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
