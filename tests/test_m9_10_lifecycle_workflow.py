"""M9.10 lifecycle TUI workflow parity tests."""

from __future__ import annotations

import unittest

from fortifylab.operations import CommandExecutionResult, OperationRunResult
from fortifylab.tui.lifecycle import LifecycleWorkflowScreen


def _result(operation_id: str, exit_code: int = 0) -> OperationRunResult:
    return OperationRunResult(
        operation_id,
        exit_code,
        (CommandExecutionResult(("bash", f"apps/{operation_id}.sh"), exit_code, "ok\n", "", 0.01),),
    )


class M910LifecycleWorkflowParityTests(unittest.TestCase):
    def test_component_screen_uses_readable_actions_before_adapter_ids(self) -> None:
        screen = LifecycleWorkflowScreen("app_lifecycle.ssc")
        rendered = screen.render()

        self.assertIn("SSC lifecycle controls", rendered)
        self.assertIn("Actions:", rendered)
        self.assertIn("1. Start / upgrade", rendered)
        self.assertIn("2. Stop", rendered)
        self.assertIn("3. Destroy (deletes data)", rendered)
        self.assertNotIn("Catalog operation:", rendered)
        self.assertNotIn("ssc.start", rendered)

    def test_arrows_and_numbers_select_user_facing_actions(self) -> None:
        screen = LifecycleWorkflowScreen("app_lifecycle.mysql")

        self.assertEqual(screen.handle_key("down").message, "Selected mysql.stop.")
        self.assertEqual(screen.handle_key("down").message, "Selected mysql.destroy.")
        self.assertEqual(screen.handle_key("up").message, "Selected mysql.stop.")
        self.assertEqual(screen.handle_key("1").message, "Selected mysql.start.")
        self.assertEqual(screen.handle_key("3").message, "Selected mysql.destroy.")

    def test_enter_prepares_plan_then_runs_safe_action_on_second_enter(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id)

        screen = LifecycleWorkflowScreen("app_lifecycle.mysql", runner=runner)
        self.assertEqual(screen.handle_key("2").message, "Selected mysql.stop.")
        self.assertEqual(screen.handle_key("enter").message, "Confirmation required before lifecycle execution.")
        self.assertIn("Plan preview", screen.render())
        self.assertIn("Continue: press enter to run this lifecycle plan.", screen.render())

        self.assertEqual(screen.handle_key("enter").message, "mysql.stop completed successfully.")
        self.assertEqual(calls, ["mysql.stop"])
        completed = screen.render()
        self.assertIn("Lifecycle status", completed)
        self.assertIn("Completion: lifecycle action finished.", completed)
        self.assertIn("Actions: enter/m Main menu", completed)

    def test_destroy_requires_typed_phrase_not_yes(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id)

        screen = LifecycleWorkflowScreen("app_lifecycle.mysql", runner=runner)
        screen.handle_key("3")
        self.assertEqual(screen.handle_key("enter").message, "Confirmation required before lifecycle execution.")
        self.assertIn("Confirm by typing: DESTROY", screen.render())
        self.assertEqual(screen.handle_key("y").message, "Type DESTROY to confirm destructive lifecycle execution.")
        self.assertEqual(calls, [])

        self.assertEqual(screen.handle_key("DESTROY").message, "mysql.destroy completed successfully.")
        self.assertEqual(calls, ["mysql.destroy"])

    def test_all_lab_start_plan_runs_each_step_in_order_with_readable_preview(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id)

        screen = LifecycleWorkflowScreen("lifecycle.start_lab", runner=runner)
        self.assertNotIn("Catalog operation:", screen.render())
        self.assertEqual(screen.handle_key("enter").message, "Confirmation required before lifecycle execution.")
        rendered = screen.render()
        self.assertIn("1. MySQL", rendered)
        self.assertIn("6. ScanCentral DAST", rendered)
        self.assertNotIn("mysql.start", rendered)
        self.assertNotIn("scancentral_dast.start", rendered)

        self.assertEqual(screen.handle_key("enter").message, "Lifecycle plan completed successfully.")
        self.assertEqual(
            calls,
            [
                "mysql.start",
                "postgresql.start",
                "ssc.start",
                "lim.start",
                "scancentral_sast.start",
                "scancentral_dast.start",
            ],
        )


    def test_default_lifecycle_run_streams_monitor_events(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id)

        screen = LifecycleWorkflowScreen("lifecycle.start_lab")
        screen.runner = runner
        self.assertEqual(screen.handle_key("enter").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(screen.handle_key("enter").message, "Lifecycle execution started.")
        self.assertEqual(screen.stage, "lifecycle_monitor")
        monitor = screen.render()
        self.assertIn("Lifecycle status", monitor)
        self.assertIn("State: running", monitor)
        self.assertIn("pending", monitor)
        self.assertNotIn("Plan preview", monitor)

        events = screen.iter_lifecycle_run_events()
        first_event = next(events)
        self.assertEqual(first_event.status, "running")
        self.assertEqual(screen.apply_lifecycle_run_event(first_event).message, "Starting MySQL.")
        self.assertIn("[cyan]MySQL | running | Starting MySQL.[/cyan]", screen.render())

        for event in events:
            screen.apply_lifecycle_run_event(event)
        self.assertEqual(screen.finish_lifecycle_plan().message, "Lifecycle plan completed successfully.")
        self.assertEqual(screen.stage, "lifecycle_complete")
        completed = screen.render()
        self.assertIn("Completion: lifecycle action finished.", completed)
        self.assertIn("Actions: enter/m Main menu", completed)
        self.assertEqual(screen.handle_key("enter").open_target, "main")
        self.assertEqual(calls, ["mysql.start", "postgresql.start", "ssc.start", "lim.start", "scancentral_sast.start", "scancentral_dast.start"])

    def test_lifecycle_monitor_stops_on_failure(self) -> None:
        def runner(operation_id: str) -> OperationRunResult:
            return _result(operation_id, 17 if operation_id == "ssc.start" else 0)

        screen = LifecycleWorkflowScreen("lifecycle.start_lab")
        screen.runner = runner
        screen.handle_key("enter")
        screen.handle_key("enter")

        for event in screen.iter_lifecycle_run_events():
            result = screen.apply_lifecycle_run_event(event)
            if screen.stage == "lifecycle_failed":
                break

        self.assertEqual(screen.stage, "lifecycle_failed")
        self.assertIn("SSC", result.message)
        self.assertEqual(screen.finish_lifecycle_plan().message, "Lifecycle stopped after SSC failed.")


    def test_lifecycle_logs_and_inspection_are_available_during_monitor(self) -> None:
        def runner(operation_id: str) -> OperationRunResult:
            return OperationRunResult(
                operation_id,
                0,
                (CommandExecutionResult(("bash", "apps/mysql/start.sh", "--token=abc123"), 0, "password=hunter2\n", "", 0.01),),
            )

        screen = LifecycleWorkflowScreen("app_lifecycle.mysql")
        screen.runner = runner
        screen.handle_key("enter")
        screen.handle_key("enter")

        for event in screen.iter_lifecycle_run_events():
            screen.apply_lifecycle_run_event(event)

        self.assertEqual(screen.handle_key("l").message, "Opened lifecycle logs.")
        rendered_logs = screen.render()
        self.assertIn("Lifecycle logs", rendered_logs)
        self.assertIn("password=<redacted>", rendered_logs)
        self.assertNotIn("hunter2", rendered_logs)
        self.assertNotIn("abc123", rendered_logs)

        self.assertEqual(screen.handle_key("i").message, "Opened lifecycle inspection.")
        rendered_inspection = screen.render()
        self.assertIn("Lifecycle inspection", rendered_inspection)
        self.assertIn("mysql.start", rendered_inspection)
        self.assertIn("bash apps/mysql/start.sh", rendered_inspection)
        self.assertIn("Pod logs: use Diagnostics or Logs handoff", rendered_inspection)

    def test_lifecycle_completion_handoff_keys_open_existing_workflows(self) -> None:
        screen = LifecycleWorkflowScreen("app_lifecycle.mysql")
        screen.runner = lambda operation_id: _result(operation_id)
        screen.handle_key("enter")
        screen.handle_key("enter")
        for event in screen.iter_lifecycle_run_events():
            screen.apply_lifecycle_run_event(event)
        screen.finish_lifecycle_plan()

        logs = screen.handle_key("1")
        diagnostics = screen.handle_key("2")
        status = screen.handle_key("3")
        main = screen.handle_key("m")

        self.assertEqual(logs.open_target, "logs")
        self.assertEqual(diagnostics.open_target, "diagnostics")
        self.assertEqual(status.open_target, "status")
        self.assertEqual(main.open_target, "main")

    def test_reset_lab_stays_deferred_on_current_menu_route(self) -> None:
        screen = LifecycleWorkflowScreen("lifecycle.reset_lab")

        self.assertIn("Unsupported:", screen.render())
        self.assertIn("scope selection", screen.handle_key("enter").message)


if __name__ == "__main__":
    unittest.main()
