"""Unit tests for LabLifecycleScreen (deployment & component management
parity: bulk shutdown/start chooser)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent, TickEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.guided_deploy import GuidedDeployScreen  # noqa: E402
from fortifylab.tui.screens.lab_lifecycle import LabLifecycleScreen  # noqa: E402
from fortifylab.tui.screens.main_menu import MainMenuScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _screen(env_dir: Path) -> LabLifecycleScreen:
    return LabLifecycleScreen(style=TerminalStyle(color=False, symbols=False), env_file=env_dir / ".env")


class LabLifecycleScreenTests(unittest.TestCase):
    def test_renders_all_four_non_destructive_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rendered = _screen(Path(directory)).render()
            self.assertIn("Shutdown selected profile workloads", rendered)
            self.assertIn("Start selected profile workloads", rendered)
            self.assertIn("Shutdown all lab deployments", rendered)
            self.assertIn("Start all lab deployments", rendered)

    def test_never_offers_destroy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rendered = _screen(Path(directory)).render()
            self.assertNotIn("Destroy", rendered)
            self.assertIn("destroy is not available here", rendered)

    def test_navigation_wraps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(Path(directory))
            screen.handle_event(KeyEvent("up"))
            self.assertEqual(screen.selected_index, 3)

    def test_enter_pushes_a_guided_deploy_screen_built_from_the_lifecycle_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(Path(directory))
            command = screen.handle_event(KeyEvent("enter"))
            self.assertEqual(command.kind, NavigationKind.PUSH)
            self.assertIsInstance(command.screen, GuidedDeployScreen)
            self.assertIn("shutdown", command.screen.service.plan.name)
            self.assertIn("selected profile", command.screen.service.plan.name)

    def test_selecting_start_all_builds_a_start_all_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(Path(directory))
            screen.selected_index = 3  # "Start all lab deployments"
            command = screen.handle_event(KeyEvent("enter"))
            self.assertIn("start", command.screen.service.plan.name)
            self.assertIn("all apps", command.screen.service.plan.name)
            step_ids = {step.step_id for step in command.screen.service.plan.steps}
            self.assertIn("ssc", step_ids)
            self.assertIn("juice-shop", step_ids)
            self.assertIn("sast", step_ids)
            self.assertIn("dast", step_ids)

    def test_on_enter_caches_scope_previews_instead_of_recomputing_on_every_render(self) -> None:
        # Regression test (code review finding): render() runs on every
        # ~0.25s TickEvent (app.py's main loop), not just on navigation.
        # apps_for_scope() re-reads .env and rebuilds/expands the active
        # guided profile -- computing it per-render meant doing that
        # up to ~16x/second just from leaving this screen open. It must
        # be computed once in on_enter() and reused across renders/ticks.
        import unittest.mock

        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(Path(directory))
            with unittest.mock.patch(
                "fortifylab.tui.screens.lab_lifecycle.apps_for_scope", wraps=lambda *a, **k: ()
            ) as mocked:
                screen.on_enter()
                calls_after_enter = mocked.call_count
                self.assertGreater(calls_after_enter, 0)

                for _ in range(5):
                    screen.render()
                    screen.handle_event(TickEvent(0.0))

                self.assertEqual(mocked.call_count, calls_after_enter)

    def test_on_enter_populates_previews_for_both_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(Path(directory))
            screen.on_enter()
            self.assertIn("selected", screen._previews)
            self.assertIn("all", screen._previews)

    def test_q_pops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            command = _screen(Path(directory)).handle_event(KeyEvent("q"))
            self.assertEqual(command.kind, NavigationKind.POP)


class MainMenuOpensLabLifecycleTests(unittest.TestCase):
    def test_o_on_lab_lifecycle_opens_lab_lifecycle_screen(self) -> None:
        menu = MainMenuScreen(style=TerminalStyle(color=False, symbols=False))
        index = next(i for i, item in enumerate(menu.items) if item.key == "lab-lifecycle")
        menu.selected_index = index
        command = menu.handle_event(KeyEvent("o"))
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, LabLifecycleScreen)


if __name__ == "__main__":
    unittest.main()
