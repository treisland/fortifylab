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
        self.assertIn("Catalog operation: ssc.start, ssc.stop, ssc.destroy", rendered)

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
        self.assertIn("Handoffs:", screen.render())
        self.assertIn("m. Main menu -> main", screen.render())

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
        self.assertIn("Catalog operation: lab.start.all", screen.render())
        self.assertEqual(screen.handle_key("enter").message, "Confirmation required before lifecycle execution.")
        rendered = screen.render()
        self.assertIn("1. MySQL -> mysql.start", rendered)
        self.assertIn("6. ScanCentral DAST -> scancentral_dast.start", rendered)

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

    def test_reset_lab_stays_deferred_on_current_menu_route(self) -> None:
        screen = LifecycleWorkflowScreen("lifecycle.reset_lab")

        self.assertIn("Unsupported:", screen.render())
        self.assertIn("scope selection", screen.handle_key("enter").message)


if __name__ == "__main__":
    unittest.main()
