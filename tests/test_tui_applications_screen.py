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
from fortifylab.services.scale_workers_service import ScaleWorkersService  # noqa: E402
from fortifylab.tui.events import KeyEvent, TickEvent  # noqa: E402
from fortifylab.tui.screens.applications import ApplicationsScreen, _Stage  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.logs import LogsScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _no_pods_status_service() -> AppStatusService:
    return AppStatusService(runner=lambda args: CommandResult(args, 1, "", "", 0.0))


def _plain_screen(*, env_dir: Path | None = None, **kwargs) -> ApplicationsScreen:
    kwargs.setdefault("status_service", _no_pods_status_service())
    kwargs.setdefault("style", TerminalStyle(color=False, symbols=False))
    if env_dir is not None:
        kwargs.setdefault("env_file", env_dir / ".env")
    elif "env_file" not in kwargs:
        # Isolate from any real .env in the working directory -- this
        # screen's __post_init__ reads NAMESPACE/URL keys from it.
        kwargs["env_file"] = Path("/nonexistent/.env")
    return ApplicationsScreen(**kwargs)


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

    def test_no_repair_hint_offered(self) -> None:
        # Destroy is now available (per-app, gated by a typed confirmation
        # phrase) -- this only guards against a leftover repair/no-destroy
        # hint the list stage used to render before that.
        screen = _plain_screen()
        self.assertNotIn("repair", screen.render())

    def test_includes_sast_and_dast_alongside_core_apps(self) -> None:
        screen = _plain_screen()
        rendered = screen.render()
        self.assertIn("ScanCentral SAST", rendered)
        self.assertIn("ScanCentral DAST", rendered)


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

    def test_offers_start_stop_logs_credentials_destroy_and_scale(self) -> None:
        # Scale workers is offered in the menu for every app, matching
        # Bash -- it's scale_workers() itself that rejects an app it
        # doesn't support, not a hidden menu entry.
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        rendered = screen.render()
        self.assertIn("Start / Upgrade", rendered)
        self.assertIn("Stop", rendered)
        self.assertIn("Logs", rendered)
        self.assertIn("Show URL & credentials", rendered)
        self.assertIn("Destroy", rendered)
        self.assertIn("Scale workers", rendered)

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

    def test_logs_action_for_sast_pushes_a_logs_screen_pinned_by_unfiltered_prefix(self) -> None:
        # SAST is a combined app row over Bash's separate controller/sensor
        # scopes -- its "Logs" action must jump via the unfiltered
        # initial_prefix, not initial_step_id (there is no single "sast"
        # entry in tui.profiles.LOG_SCOPES).
        screen = _plain_screen()
        _enter_app_menu(screen, "sast")
        _select_action(screen, "logs")
        command = screen.handle_event(KeyEvent("enter"))
        self.assertEqual(command.kind, NavigationKind.PUSH)
        self.assertIsInstance(command.screen, LogsScreen)
        self.assertIsNone(command.screen.initial_step_id)
        self.assertEqual(command.screen.initial_prefix, "scancentral-sast")

    def test_logs_action_for_dast_pushes_a_logs_screen_pinned_by_unfiltered_prefix(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "dast")
        _select_action(screen, "logs")
        command = screen.handle_event(KeyEvent("enter"))
        self.assertEqual(command.screen.initial_prefix, "sdast")

    def test_destroy_action_enters_a_confirmation_stage_instead_of_running_immediately(self) -> None:
        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(lambda c: CommandResult(c, 0, "ok", "", 0.0)))
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "destroy")
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(screen.stage, _Stage.CONFIRM_DESTROY)
        self.assertFalse(screen.is_executing)
        rendered = screen.render()
        self.assertIn("Destroy Software Security Center", rendered)
        self.assertIn("DESTROY ssc", rendered)

    def test_typing_into_the_confirm_field_appends_characters(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "destroy")
        screen.handle_event(KeyEvent("enter"))
        for char in "DESTROY ssc":
            screen.handle_event(KeyEvent(char))
        self.assertEqual(screen.confirm_field.value, "DESTROY ssc")
        self.assertIn("DESTROY ssc", screen.render())

    def test_escape_from_confirm_destroy_cancels_back_to_the_app_menu_without_running(self) -> None:
        release_calls: list[tuple[str, ...]] = []
        screen = _plain_screen(
            catalog=OperationCatalog(), runner=OperationRunner(lambda c: release_calls.append(c) or CommandResult(c, 0, "ok", "", 0.0))
        )
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "destroy")
        screen.handle_event(KeyEvent("enter"))
        for char in "DESTROY ssc":
            screen.handle_event(KeyEvent(char))
        screen.handle_event(KeyEvent("escape"))
        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertFalse(screen.is_executing)
        self.assertEqual(release_calls, [])

    def test_wrong_confirmation_phrase_is_rejected_without_destroying_anything(self) -> None:
        calls: list[tuple[str, ...]] = []
        screen = _plain_screen(
            catalog=OperationCatalog(), runner=OperationRunner(lambda c: calls.append(c) or CommandResult(c, 0, "destroyed", "", 0.0))
        )
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "destroy")
        screen.handle_event(KeyEvent("enter"))
        for char in "not the right phrase":
            screen.handle_event(KeyEvent(char))
        screen.handle_event(KeyEvent("enter"))

        _wait_for_execution(screen)

        self.assertFalse(screen.last_execution.executed)
        self.assertFalse(screen.last_execution.ok)
        self.assertIn("DESTROY ssc", screen.last_execution.detail)
        self.assertEqual(calls, [])  # the underlying script never ran

    def test_correct_confirmation_phrase_runs_destroy_in_the_background(self) -> None:
        release = threading.Event()

        def slow_runner(command):
            release.wait(timeout=2.0)
            return CommandResult(args=command, returncode=0, stdout="destroyed", stderr="", duration_seconds=0.0)

        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(slow_runner))
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "destroy")
        screen.handle_event(KeyEvent("enter"))
        for char in "DESTROY ssc":
            screen.handle_event(KeyEvent(char))

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertTrue(screen.is_executing)
        release.set()
        _wait_for_execution(screen)
        self.assertTrue(screen.last_execution.executed)
        self.assertTrue(screen.last_execution.ok)
        self.assertEqual(screen.last_execution.operation_id, "app.ssc.destroy")

    def test_confirm_destroy_shows_a_busy_message_while_a_previous_submission_is_still_in_flight(self) -> None:
        # Regression test (code review finding): pressing enter on a
        # confirm-destroy screen while a previous submission (this app's
        # rejected phrase, or another app's destroy) is still executing
        # used to be a silent no-op -- nothing told the operator why
        # nothing happened.
        release = threading.Event()

        def slow_runner(command):
            release.wait(timeout=2.0)
            return CommandResult(args=command, returncode=0, stdout="destroyed", stderr="", duration_seconds=0.0)

        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(slow_runner))
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "destroy")
        screen.handle_event(KeyEvent("enter"))
        for char in "DESTROY ssc":
            screen.handle_event(KeyEvent(char))
        screen.handle_event(KeyEvent("enter"))  # dispatches in the background, is_executing=True

        # Re-open the confirm screen for the same app while still executing.
        screen.stage = _Stage.CONFIRM_DESTROY
        rendered = screen.render()
        self.assertIn("Still processing a previous request", rendered)

        release.set()
        _wait_for_execution(screen)

    def test_scale_workers_shows_not_supported_for_a_non_scancentral_app(self) -> None:
        # Bash's scale_workers() offers this option in the same menu for
        # every app and lets the function itself reject one it doesn't
        # support (SSC, LIM, MySQL, PostgreSQL, and every sample app all
        # fall through its case statement's default branch).
        calls: list[tuple[str, ...]] = []
        screen = _plain_screen(scale_service=ScaleWorkersService(runner=lambda args: calls.append(args) or CommandResult(args, 0, "", "", 0.0)))
        _enter_app_menu(screen, "ssc")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertIn("Scaling not supported", screen.last_execution.detail)
        self.assertEqual(calls, [])

    def test_scale_workers_enters_a_stage_showing_current_replicas_for_sast(self) -> None:
        screen = _plain_screen(scale_service=ScaleWorkersService(runner=lambda args: CommandResult(args, 0, "3", "", 0.0)))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(screen.stage, _Stage.SCALE_WORKERS)
        rendered = screen.render()
        self.assertIn("Scale workers -- ScanCentral SAST", rendered)
        self.assertIn("Current replicas: 3", rendered)

    def test_empty_replica_count_cancels_silently(self) -> None:
        calls: list[tuple[str, ...]] = []
        screen = _plain_screen(scale_service=ScaleWorkersService(runner=lambda args: calls.append(args) or CommandResult(args, 0, "1", "", 0.0)))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))  # -> SCALE_WORKERS, current_replicas call
        calls.clear()

        screen.handle_event(KeyEvent("enter"))  # empty value -> cancel

        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertIsNone(screen.last_execution)
        self.assertEqual(calls, [])

    def test_non_numeric_replica_count_is_rejected_without_scaling(self) -> None:
        calls: list[tuple[str, ...]] = []
        screen = _plain_screen(scale_service=ScaleWorkersService(runner=lambda args: calls.append(args) or CommandResult(args, 0, "1", "", 0.0)))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))
        calls.clear()
        for char in "abc":
            screen.handle_event(KeyEvent(char))

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertIn("Not a number", screen.last_execution.detail)
        self.assertEqual(calls, [])

    def test_valid_replica_count_scales_the_statefulset_in_the_background(self) -> None:
        # Regression test (code review finding): a kubectl scale call is
        # normally near-instant, but KubectlBackedService._run() still
        # carries a real 20s timeout -- scale must go through the same
        # background-thread/poll mechanism as start/stop/destroy so a
        # slow or unreachable cluster can't freeze the whole TUI.
        release = threading.Event()
        calls: list[tuple[str, ...]] = []

        def runner(args):
            calls.append(args)
            if "get" in args:
                return CommandResult(args, 0, "1", "", 0.0)
            release.wait(timeout=2.0)
            return CommandResult(args, 0, "scaled", "", 0.0)

        screen = _plain_screen(catalog=OperationCatalog(), scale_service=ScaleWorkersService(runner=runner))
        _enter_app_menu(screen, "dast")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))
        for char in "4":
            screen.handle_event(KeyEvent(char))

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertTrue(screen.is_executing)
        release.set()
        _wait_for_execution(screen)
        self.assertTrue(screen.last_execution.executed)
        self.assertTrue(screen.last_execution.ok)
        self.assertEqual(
            screen.last_execution.command,
            ("microk8s", "kubectl", "-n", "fortify", "scale", "statefulset", "sdast-scanner-scancentral-dast-scanner", "--replicas=4"),
        )
        scale_calls = [c for c in calls if "scale" in c]
        self.assertEqual(
            scale_calls[0],
            ("-n", "fortify", "scale", "statefulset", "sdast-scanner-scancentral-dast-scanner", "--replicas=4"),
        )

    def test_non_ascii_digit_replica_count_is_rejected_without_scaling(self) -> None:
        # Regression test (code review finding): str.isdigit() alone
        # accepts non-ASCII digit characters (Arabic-indic, full-width)
        # that Bash's ASCII-only ^[0-9]+$ regex would reject -- those must
        # not reach kubectl's --replicas flag.
        calls: list[tuple[str, ...]] = []
        screen = _plain_screen(scale_service=ScaleWorkersService(runner=lambda args: calls.append(args) or CommandResult(args, 0, "1", "", 0.0)))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))
        calls.clear()
        screen.handle_event(KeyEvent("４"))  # full-width "4"

        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertIn("Not a number", screen.last_execution.detail)
        self.assertEqual(calls, [])

    def test_scale_action_is_blocked_while_another_execution_is_in_flight(self) -> None:
        release = threading.Event()

        def slow_runner(command):
            release.wait(timeout=2.0)
            return CommandResult(args=command, returncode=0, stdout="started", stderr="", duration_seconds=0.0)

        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(slow_runner))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "start")
        screen.toggle_armed()
        screen.handle_event(KeyEvent("enter"))
        self.assertTrue(screen.is_executing)

        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))

        self.assertEqual(screen.stage, _Stage.APP_MENU)  # never entered SCALE_WORKERS
        release.set()
        _wait_for_execution(screen)

    def test_escape_from_scale_workers_cancels_without_scaling(self) -> None:
        calls: list[tuple[str, ...]] = []
        screen = _plain_screen(scale_service=ScaleWorkersService(runner=lambda args: calls.append(args) or CommandResult(args, 0, "1", "", 0.0)))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "scale")
        screen.handle_event(KeyEvent("enter"))
        calls.clear()
        screen.handle_event(KeyEvent("5"))

        screen.handle_event(KeyEvent("escape"))

        self.assertEqual(screen.stage, _Stage.APP_MENU)
        self.assertEqual(calls, [])

    def test_destroy_row_is_styled_as_a_warning_in_the_app_menu(self) -> None:
        screen = _plain_screen(style=TerminalStyle(color=True, symbols=True))
        _enter_app_menu(screen, "ssc")
        rendered = screen.render()
        destroy_line = next(line for line in rendered.splitlines() if "Destroy" in line)
        self.assertIn("[33m", destroy_line)

    def test_sast_start_uses_the_real_start_script_via_bash(self) -> None:
        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(lambda c: CommandResult(c, 0, "ok", "", 0.0)))
        _enter_app_menu(screen, "sast")
        _select_action(screen, "start")
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(screen.last_execution.command, ("bash", "./apps/scsast/start.sh"))

    def test_dast_start_chains_core_then_scanner_scripts(self) -> None:
        screen = _plain_screen(catalog=OperationCatalog(), runner=OperationRunner(lambda c: CommandResult(c, 0, "ok", "", 0.0)))
        _enter_app_menu(screen, "dast")
        _select_action(screen, "start")
        screen.handle_event(KeyEvent("enter"))
        self.assertEqual(
            screen.last_execution.command,
            ("bash", "-c", "bash ./apps/scdast/core/start.sh && bash ./apps/scdast/scanner/start.sh"),
        )

    def test_credentials_toggle_shows_login_hint_for_sast(self) -> None:
        screen = _plain_screen()
        _enter_app_menu(screen, "sast")
        _select_action(screen, "credentials")
        screen.handle_event(KeyEvent("enter"))
        rendered = screen.render()
        self.assertIn("Tokens", rendered)

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
