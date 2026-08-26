"""M9.4 lifecycle TUI contract tests.

These tests prove menu-to-operation mapping, dry-run previews, confirmation
gates, redacted result display, and injected runners without invoking
Kubernetes, Helm, Docker, or repository lifecycle scripts.
"""

from __future__ import annotations

import unittest

from fortifylab.operations import CommandExecutionResult, OperationRunResult
from fortifylab.tui.lifecycle import (
    LifecycleWorkflowScreen,
    build_dry_run_preview,
    build_result_display,
    resolve_lifecycle_action,
)
from fortifylab.tui.workflows import dispatch_menu_item
from fortifylab.navigation import find_item


class M9LifecycleContractTests(unittest.TestCase):
    def test_app_lifecycle_targets_map_to_catalog_operations(self) -> None:
        cases = {
            "app_lifecycle.mysql": ("mysql.start", "mysql.stop", "mysql.destroy"),
            "app_lifecycle.postgresql": ("postgresql.start", "postgresql.stop", "postgresql.destroy"),
            "app_lifecycle.ssc": ("ssc.start", "ssc.stop", "ssc.destroy"),
            "app_lifecycle.lim": ("lim.start", "lim.stop", "lim.destroy"),
            "app_lifecycle.scancentral_sast": (
                "scancentral_sast.start",
                "scancentral_sast.stop",
                "scancentral_sast.destroy",
            ),
            "app_lifecycle.scancentral_dast": (
                "scancentral_dast.start",
                "scancentral_dast.stop",
                "scancentral_dast.destroy",
            ),
        }

        for action_target, operation_ids in cases.items():
            with self.subTest(action_target=action_target):
                contract = resolve_lifecycle_action(action_target)
                self.assertTrue(contract.supported)
                self.assertEqual(contract.operation_ids, operation_ids)

    def test_sample_app_targets_map_to_catalog_operations(self) -> None:
        for prefix in ("app_lifecycle", "sample_apps"):
            with self.subTest(prefix=prefix):
                contract = resolve_lifecycle_action(f"{prefix}.juice_shop")
                self.assertEqual(
                    contract.operation_ids,
                    ("juice_shop.start", "juice_shop.stop", "juice_shop.destroy"),
                )

    def test_lab_lifecycle_contract_marks_unsupported_sequences_safe(self) -> None:
        self.assertEqual(resolve_lifecycle_action("lifecycle.start_lab").operation_ids, ("lab.start.all",))
        self.assertEqual(resolve_lifecycle_action("lifecycle.stop_lab").operation_ids, ("lab.stop.all",))

        for action_target in ("lifecycle.restart_lab", "lifecycle.reset_lab"):
            with self.subTest(action_target=action_target):
                contract = resolve_lifecycle_action(action_target)
                self.assertFalse(contract.supported)
                self.assertEqual(contract.operation_ids, ())
                self.assertIsNotNone(contract.unsupported_reason)

    def test_dry_run_preview_model_does_not_execute_lifecycle_scripts(self) -> None:
        preview = build_dry_run_preview("app_lifecycle.mysql", "mysql.destroy")

        self.assertEqual(preview.action_target, "app_lifecycle.mysql")
        self.assertEqual(preview.operation_id, "mysql.destroy")
        self.assertTrue(preview.mutating)
        self.assertTrue(preview.confirmation_required)
        self.assertEqual(preview.commands, ("bash apps/mysql/destroy.sh",))
        self.assertIn("DESTROY", preview.confirmation_prompt or "")

    def test_dispatch_opens_lifecycle_contract_screen_without_changing_navigation(self) -> None:
        selected = find_item("app_lifecycle", "1")
        assert selected is not None

        result = dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertEqual(result.screen.title, "MySQL")
        self.assertIn("mysql.start", result.screen.render())

    def test_screen_preview_and_confirmation_do_not_call_runner_until_yes(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return OperationRunResult(operation_id, 0, ())

        screen = LifecycleWorkflowScreen("app_lifecycle.mysql", runner=runner)

        self.assertEqual(screen.handle_key("2").message, "Selected mysql.stop.")
        self.assertEqual(screen.handle_key("p").message, "Previewed mysql.stop.")
        self.assertEqual(calls, [])
        self.assertEqual(screen.handle_key("c").message, "Confirmation required before lifecycle execution.")
        self.assertEqual(calls, [])
        self.assertEqual(screen.handle_key("y").message, "mysql.stop completed successfully.")
        self.assertEqual(calls, ["mysql.stop"])

    def test_result_display_summarizes_exit_code_and_redacted_output(self) -> None:
        result = OperationRunResult(
            "mysql.start",
            7,
            (
                CommandExecutionResult(
                    ("bash", "apps/mysql/start.sh"),
                    7,
                    "created pod\npassword=hunter2\n",
                    "token=abc123\nfailed\n",
                    0.1,
                ),
            ),
        )

        display = build_result_display(result)

        self.assertEqual(display.status, "failure")
        self.assertEqual(display.exit_code, 7)
        self.assertIn("created pod", display.stdout_summary)
        self.assertIn("failed", display.stderr_summary)
        self.assertIn("password=<redacted>", "\n".join(display.redacted_output))
        self.assertNotIn("hunter2", "\n".join(display.redacted_output))
        self.assertNotIn("abc123", "\n".join(display.redacted_output))

    def test_unsupported_lifecycle_screen_is_safe(self) -> None:
        screen = LifecycleWorkflowScreen("lifecycle.reset_lab")

        self.assertIn("Unsupported:", screen.render())
        self.assertIn("scope selection", screen.handle_key("y").message)


if __name__ == "__main__":
    unittest.main()
