"""Focused M9.4 lifecycle TUI workflow tests.

These tests cover the implementation-facing behavior after the M9.4 contract:
selection, preview/confirmation gating, injected runner results, redaction, and
navigation dispatch. They use mocked runners only and never invoke live app,
Kubernetes, Helm, or Docker scripts.
"""

from __future__ import annotations

import unittest

from fortifylab.navigation import find_item
from fortifylab.operations import CommandExecutionResult, OperationRunResult
from fortifylab.tui.lifecycle import LifecycleWorkflowScreen
from fortifylab.tui.workflows import dispatch_menu_item


def _result(
    operation_id: str,
    exit_code: int,
    *,
    stdout: str = "",
    stderr: str = "",
    command: tuple[str, ...] = ("bash", "apps/mysql/start.sh"),
) -> OperationRunResult:
    return OperationRunResult(
        operation_id,
        exit_code,
        (
            CommandExecutionResult(
                command,
                exit_code,
                stdout,
                stderr,
                0.01,
            ),
        ),
    )


class M9LifecycleWorkflowTests(unittest.TestCase):
    def test_operation_selection_by_number_updates_preview_target(self) -> None:
        screen = LifecycleWorkflowScreen("app_lifecycle.mysql", runner=lambda operation_id: _result(operation_id, 0))

        self.assertEqual(screen.handle_key("1").message, "Selected mysql.start.")
        self.assertEqual(screen.handle_key("p").message, "Previewed mysql.start.")
        assert screen.last_preview is not None
        self.assertEqual(screen.last_preview.operation_id, "mysql.start")

        self.assertEqual(screen.handle_key("2").message, "Selected mysql.stop.")
        self.assertEqual(screen.handle_key("p").message, "Previewed mysql.stop.")
        assert screen.last_preview is not None
        self.assertEqual(screen.last_preview.operation_id, "mysql.stop")

        self.assertEqual(screen.handle_key("3").message, "Selected mysql.destroy.")
        self.assertEqual(screen.handle_key("d").message, "Previewed mysql.destroy.")
        assert screen.last_preview is not None
        self.assertEqual(screen.last_preview.operation_id, "mysql.destroy")
        self.assertEqual(screen.last_preview.commands, ("bash apps/mysql/destroy.sh",))

    def test_operation_selection_by_arrows_updates_preview_target(self) -> None:
        screen = LifecycleWorkflowScreen("app_lifecycle.mysql", runner=lambda operation_id: _result(operation_id, 0))

        self.assertEqual(screen.selected_operation_id, "mysql.start")
        self.assertEqual(screen.handle_key("down").message, "Selected mysql.stop.")
        self.assertEqual(screen.handle_key("p").message, "Previewed mysql.stop.")
        assert screen.last_preview is not None
        self.assertEqual(screen.last_preview.operation_id, "mysql.stop")

        self.assertEqual(screen.handle_key("down").message, "Selected mysql.destroy.")
        self.assertEqual(screen.handle_key("down").message, "Selected mysql.start.")
        self.assertEqual(screen.handle_key("up").message, "Selected mysql.destroy.")
        self.assertEqual(screen.handle_key("p").message, "Previewed mysql.destroy.")
        assert screen.last_preview is not None
        self.assertEqual(screen.last_preview.operation_id, "mysql.destroy")

    def test_preview_and_direct_yes_are_gated_before_runner_execution(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id, 0)

        screen = LifecycleWorkflowScreen("app_lifecycle.postgresql", runner=runner)

        self.assertEqual(screen.handle_key("p").message, "Previewed postgresql.start.")
        self.assertEqual(calls, [])

        self.assertIn("No lifecycle action", screen.handle_key("y").message)
        self.assertEqual(calls, [])

        self.assertEqual(screen.handle_key("c").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(calls, [])

    def test_cancel_clears_confirmation_without_running_operation(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id, 0)

        screen = LifecycleWorkflowScreen("app_lifecycle.ssc", runner=runner)

        self.assertEqual(screen.handle_key("c").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(screen.handle_key("n").message, "Lifecycle execution cancelled.")
        self.assertEqual(calls, [])

        self.assertIn("No lifecycle action", screen.handle_key("y").message)
        self.assertEqual(calls, [])

    def test_confirm_with_injected_runner_records_success_result(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id, 0, stdout="started cleanly\n")

        screen = LifecycleWorkflowScreen("sample_apps.juice_shop", runner=runner)

        self.assertEqual(screen.handle_key("2").message, "Selected juice_shop.stop.")
        self.assertEqual(screen.handle_key("enter").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(screen.handle_key("y").message, "juice_shop.stop completed successfully.")

        self.assertEqual(calls, ["juice_shop.stop"])
        assert screen.last_result is not None
        self.assertEqual(screen.last_result.status, "success")
        self.assertEqual(screen.last_result.exit_code, 0)
        self.assertIn("started cleanly", screen.render())

    def test_confirm_with_injected_runner_records_failure_result(self) -> None:
        def runner(operation_id: str) -> OperationRunResult:
            return _result(operation_id, 42, stderr="helm failed\n")

        screen = LifecycleWorkflowScreen("sample_apps.webgoat", runner=runner)

        self.assertEqual(screen.handle_key("3").message, "Selected webgoat.destroy.")
        self.assertEqual(screen.handle_key("c").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(screen.handle_key("y").message, "webgoat.destroy failed with exit code 42.")

        assert screen.last_result is not None
        self.assertEqual(screen.last_result.status, "failure")
        self.assertEqual(screen.last_result.exit_code, 42)
        rendered = screen.render()
        self.assertIn("Exit code: 42", rendered)
        self.assertIn("stderr: helm failed", rendered)

    def test_runner_output_is_redacted_before_display(self) -> None:
        def runner(operation_id: str) -> OperationRunResult:
            return _result(
                operation_id,
                1,
                stdout="password=hunter2\nAuthorization: Bearer abc.def\n",
                stderr="token=secret-token\nsee /home/tre/.ssh/github-treisland-agent\n",
                command=("bash", "apps/lim/start.sh", "--token", "abc.def"),
            )

        screen = LifecycleWorkflowScreen("app_lifecycle.lim", runner=runner)

        self.assertEqual(screen.handle_key("c").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(screen.handle_key("y").message, "lim.start failed with exit code 1.")

        assert screen.last_result is not None
        combined_output = "\n".join((*screen.last_result.redacted_output, screen.render()))
        self.assertIn("password=<redacted>", combined_output)
        self.assertIn("Authorization: Bearer <redacted>", combined_output)
        self.assertIn("token=<redacted>", combined_output)
        self.assertIn("<sensitive-path>", combined_output)
        self.assertNotIn("hunter2", combined_output)
        self.assertNotIn("secret-token", combined_output)
        self.assertNotIn("/home/tre/.ssh/github-treisland-agent", combined_output)

    def test_unsupported_restart_and_reset_do_not_call_runner(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id, 0)

        for action_target in ("lifecycle.restart_lab", "lifecycle.reset_lab"):
            with self.subTest(action_target=action_target):
                screen = LifecycleWorkflowScreen(action_target, runner=runner)
                self.assertIn("Unsupported:", screen.render())
                self.assertIn("needs", screen.handle_key("c").message.lower())
                self.assertIn("needs", screen.handle_key("y").message.lower())

        self.assertEqual(calls, [])

    def test_lifecycle_dispatch_from_preserved_menus_opens_workflow_screens(self) -> None:
        cases = (
            ("lifecycle", "1", "lifecycle:lifecycle.start_lab", "lab.start.all"),
            ("lifecycle", "2", "lifecycle:lifecycle.stop_lab", "lab.stop.all"),
            ("app_lifecycle", "5", "lifecycle:app_lifecycle.scancentral_sast", "scancentral_sast.start"),
            ("app_lifecycle", "9", "lifecycle:app_lifecycle.dvwa", "dvwa.start"),
            ("sample_apps", "1", "lifecycle:sample_apps.juice_shop", "juice_shop.start"),
            ("sample_apps", "3", "lifecycle:sample_apps.dvwa", "dvwa.start"),
        )

        for menu_id, key, screen_id, rendered_operation in cases:
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None

                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertEqual(result.screen.id, screen_id)
                self.assertIn(rendered_operation, result.screen.render())


if __name__ == "__main__":
    unittest.main()
