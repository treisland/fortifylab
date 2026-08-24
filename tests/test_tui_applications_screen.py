"""Unit tests for ApplicationsScreen: list of apps with live status ->
per-app menu (Start/Stop/Logs/Show URL & credentials), matching Bash's
apps_menu()/app_action_menu() shape (#446, deployment & component
management parity)."""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.operations import OperationCatalog, OperationRunner  # noqa: E402
from fortifylab.services.app_status_service import AppStatusService  # noqa: E402
from fortifylab.tui.events import KeyEvent, TickEvent  # noqa: E402
from fortifylab.tui.screens.applications import ApplicationsScreen, _Stage  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.logs import LogsScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _no_pods_status_service() -> AppStatusService:
    return AppStatusService(runner=lambda args: CommandResult(args, 1, "", "", 0.0))


def _plain_screen(*, env_dir: Path | None = None, **kwargs) -> ApplicationsScreen:
    kwargs.setdefault("status_service", _no_pods_status_service())
    if env_dir is not None:
        kwargs.setdefault("env_file", env_dir / ".env")
    elif "env_file" not in kwargs:
        # Isolate from any real .env in the working directory -- this
        # screen's __post_init__ reads NAMESPACE/URL keys from it.
        kwargs["env_file"] = Path("/nonexistent/.env")
    return ApplicationsScreen(style=TerminalStyle(color=False, symbols=False), **kwargs)


def _wait_for_execution(screen: ApplicationsScreen, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while screen.is_executing:
        if time.monotonic() > deadline:
            raise AssertionError("background execution did not finish within the test timeout")
        screen.handle_event(TickEvent(0.0))
        time.sleep(0.01)


def _enter_app_menu(screen: ApplicationsScreen, app_id: str) -> None:
    index = next(i for i, (aid, *_r) in enumerate(screen.apps) if aid == app_id)
    screen.selected_app_index = index
    screen.handle_event(KeyEvent("enter"))


def _select_action(screen: ApplicationsScreen, action_id: str) -> None:
    from fortifylab.tui.screens.applications import _APP_ACTIONS

    index = next(i for i, (aid, _l) in enumerate(_APP_ACTIONS) if aid == action_id)
    screen.selected_action_index = index


class ApplicationsListStageTests(unittest.TestCase):
    def test_renders_every_app_with_live_status(self) -> None:
        service = AppStatusService(
            runner=lambda args: CommandResult(args, 0, "ssc-webapp-0   1/1   Running   0   1h\n", "", 0.0)
        )
        screen = _plain_screen(status_service=service)
        rendered = screen.render()
        self.assertIn("Software Security Center", rendered)
        self.assertIn("1/1 running", rendered)
        self.assertIn("not deployed", rendered)  # everything else has no matching pods

    def test_includes_sample_apps_alongside_core_apps(self) -> None:
        screen = _plain_screen()
        rendered = screen.render()
        for label in ("Juice Shop (sample)", "WebGoat (sample)", "DVWA (sample)"):
            self.assertIn(label, rendered)

    def test_r_refreshes_status(self) -> None:
        calls = []

        def runner(args):
            calls.append(args)
            return CommandResult(args, 1, "", "", 0.0)

        screen = _plain_screen(status_service=AppStatusService(runner=runner))
        calls.clear()  # drop the __post_init__ refresh
        screen.handle_event(KeyEvent("r"))
        self.assertEqual(len(calls), 1)

    def test_navigation_wraps(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("up"))
        self.assertEqual(screen.selected_app_index, len(screen.apps) - 1)

    def test_enter_opens_the_app_menu(self) -> None:
        screen = _plain_screen()
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(screen.stage, _Stage.APP_MENU)

    def test_q_pops(self) -> None:
        screen = _plain_screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)

    def test_no_repair_or_destroy_hint_offered(self) -> None:
        screen = _plain_screen()
        self.assertIn("destroy is not available here", screen.render())


class ApplicationsAppMenuTests(unittest.TestCase):
    def test_shows_status_and_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("SSC_URL=https://ssc.example.com\n", encoding="utf-8")
            service = AppStatusService(
                runner=lambda args: CommandResult(args, 0, "ssc-webapp-0   1/1   Running   0   1h\n", "", 0.0)
            )
            screen = _plain_screen(status_service=service, env_file=env_file)
            _enter_app_menu(screen, "ssc")
            rendered = screen.render()
            self.assertIn("1/1 running", rendered)
            self.assertIn("https://ssc.example.com", rendered)

    def test_no_url_key_for_mysql_shows_no_url_line(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "mysql")
        rendered = screen.render()
        self.assertNotIn("URL:", rendered)

    def test_offers_start_stop_logs_and_credentials_but_not_destroy_or_scale(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        rendered = screen.render()
        self.assertIn("Start / Upgrade", rendered)
        self.assertIn("Stop", rendered)
        self.assertIn("Logs", rendered)
        self.assertIn("Show URL & credentials", rendered)
        self.assertNotIn("Destroy", rendered)
        self.assertNotIn("Scale", rendered)

    def test_credentials_toggle_shows_login_hint_for_ssc(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "credentials")
        screen.handle_event(KeyEvent("enter"))
        rendered = screen.render()
        self.assertIn("admin", rendered)
        self.assertIn("SSC documentation", rendered)

    def test_credentials_toggle_off_hides_login_hint(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "credentials")
        screen.handle_event(KeyEvent("enter"))
        screen.handle_event(KeyEvent("enter"))
        self.assertFalse(screen.show_credentials)

    def test_logs_action_pushes_a_logs_screen_pinned_to_this_app(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "logs")
        command = screen.handle_event(KeyEvent("enter"))
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, LogsScreen)
        self.assertEqual(command.screen.initial_step_id, "ssc")

    def test_enter_when_armed_on_start_executes_in_background_and_shows_running(self) -> None:
        release = threading.Event()

        def slow_runner(command):
            release.wait(timeout=2.0)
            return CommandResult(args=command, returncode=0, stdout="started", stderr="", duration_seconds=0.0)

        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(slow_runner))
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "start")
        screen.toggle_armed()

        screen.handle_event(KeyEvent("enter"))

        self.assertTrue(screen.is_executing)
        self.assertIn("running", screen.render())
        release.set()
        _wait_for_execution(screen)
        self.assertTrue(screen.last_execution.ok)
        self.assertIn("app.ssc.start", screen.last_execution.operation_id)

    def test_enter_when_armed_auto_disarms(self) -> None:
        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(lambda c: CommandResult(c, 0, "ok", "", 0.0)))
        _enter_app_menu(screen, "mysql")
        _select_action(screen, "stop")
        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))
        self.assertFalse(screen.armed)
        _wait_for_execution(screen)
        self.assertTrue(screen.last_execution.ok)

    def test_enter_in_dry_run_mode_previews_without_executing(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "start")
        screen.handle_event(KeyEvent("enter"))
        self.assertIsNotNone(screen.last_execution)
        self.assertFalse(screen.last_execution.executed)

    def test_enter_while_already_executing_does_not_start_a_second_run(self) -> None:
        release = threading.Event()
        calls: list[tuple[str, ...]] = []

        def slow_runner(command):
            calls.append(command)
            release.wait(timeout=2.0)
            return CommandResult(args=command, returncode=0, stdout="started", stderr="", duration_seconds=0.0)

        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(slow_runner))
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "start")
        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(screen.is_executing)

        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))

        release.set()
        _wait_for_execution(screen)
        self.assertEqual(len(calls), 1)

    def test_navigating_actions_disarms(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        screen.handle_event(KeyEvent("a"))
        self.assertTrue(screen.armed)
        screen.handle_event(KeyEvent("down"))
        self.assertFalse(screen.armed)

    def test_r_returns_to_the_list(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        screen.handle_event(KeyEvent("r"))
        self.assertEqual(screen.stage, _Stage.LIST)

    def test_q_pops_all_the_way_out(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
