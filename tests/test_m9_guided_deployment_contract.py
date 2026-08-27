"""M9.7 guided deployment workflow contract tests.

These tests are clone-safe: they use injected fake runners and never invoke
Kubernetes, Helm, Docker, network, credentials, or live lab operations.
"""

from __future__ import annotations

import unittest

from fortifylab.navigation import find_item
from fortifylab.operations import CommandExecutionResult, OperationRunResult
from fortifylab.tui import workflows
from fortifylab.tui.guided_deployment import (
    COMPLETION_HANDOFFS,
    DEPLOYMENT_MODES,
    DEPLOYMENT_PROFILES,
    GuidedDeploymentPhase,
    GuidedDeploymentScreen,
    GuidedStepStatus,
    build_guided_deployment_snapshot,
    build_step_preview,
    deployment_steps_for_profile,
)


def _result(operation_id: str, exit_code: int = 0) -> OperationRunResult:
    return OperationRunResult(
        operation_id,
        exit_code,
        (
            CommandExecutionResult(
                ("bash", "apps/mysql/start.sh"),
                exit_code,
                "started\n" if exit_code == 0 else "",
                "" if exit_code == 0 else "failed\n",
                0.01,
            ),
        ),
    )


class M9GuidedDeploymentContractTests(unittest.TestCase):
    def test_snapshot_defines_profiles_modes_steps_and_initial_state(self) -> None:
        snapshot = build_guided_deployment_snapshot(profile_id="sast_full", mode_id="fresh")

        self.assertEqual(snapshot.phase, GuidedDeploymentPhase.PROFILE)
        self.assertEqual(snapshot.profile.id, "sast_full")
        self.assertEqual(snapshot.mode.id, "fresh")
        self.assertEqual(snapshot.steps[0].id, "mysql")
        self.assertIn("juice_shop", [step.id for step in snapshot.steps])
        self.assertEqual(snapshot.step_statuses[0], GuidedStepStatus.READY)
        self.assertTrue({profile.id for profile in DEPLOYMENT_PROFILES} >= {"core", "sast_full", "dast_full"})
        self.assertTrue({mode.id for mode in DEPLOYMENT_MODES} >= {"fresh", "resume", "repair", "component"})

    def test_profiles_expand_to_existing_operation_adapter_ids(self) -> None:
        steps = deployment_steps_for_profile("core")

        self.assertEqual(
            [step.operation_id for step in steps],
            [
                "mysql.start",
                "postgresql.start",
                "ssc.start",
                "lim.start",
                "scancentral_sast.start",
                "scancentral_dast.start",
            ],
        )

    def test_step_preview_is_dry_run_only(self) -> None:
        step = deployment_steps_for_profile("core")[0]

        preview = build_step_preview(step)

        self.assertEqual(preview.step_id, "mysql")
        self.assertEqual(preview.operation_id, "mysql.start")
        self.assertEqual(preview.commands, ("bash apps/mysql/start.sh",))
        self.assertTrue(preview.confirmation_required)
        self.assertIn("Confirm", preview.confirmation_prompt or "")

    def test_screen_selection_supports_numbers_arrows_profiles_modes_and_steps(self) -> None:
        screen = GuidedDeploymentScreen()

        self.assertEqual(screen.handle_key("2").message, "Selected profile SAST Full Lab.")
        self.assertEqual(screen.snapshot.profile.id, "sast_full")

        self.assertEqual(screen.handle_key("m").message, "Deployment mode selection.")
        self.assertEqual(screen.handle_key("2").message, "Selected mode Resume deployment.")
        self.assertEqual(screen.snapshot.mode.id, "resume")

        self.assertEqual(screen.handle_key("s").message, "Per-step controls.")
        self.assertEqual(screen.handle_key("down").message, "Selected step PostgreSQL.")
        self.assertEqual(screen.handle_key("3").message, "Selected step SSC.")
        self.assertEqual(screen.snapshot.current_step.id, "ssc")

    def test_preview_and_cancel_do_not_call_runner(self) -> None:
        calls: list[str] = []
        screen = GuidedDeploymentScreen(runner=lambda operation_id: calls.append(operation_id) or _result(operation_id))

        self.assertIn("Previewed mysql.start", screen.handle_key("v").message)
        self.assertEqual(calls, [])
        self.assertEqual(screen.snapshot.phase, GuidedDeploymentPhase.PREVIEW)

        self.assertEqual(screen.handle_key("c").message, "Confirmation required before guided deployment execution.")
        self.assertEqual(screen.handle_key("n").message, "Guided deployment step cancelled.")
        self.assertEqual(calls, [])
        self.assertEqual(screen.snapshot.step_statuses[0], GuidedStepStatus.CANCELLED)

    def test_runner_requires_confirmation_and_uses_fake_runner_boundary(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _result(operation_id)

        screen = GuidedDeploymentScreen(runner=runner)

        self.assertIn("requires preview and confirmation", screen.handle_key("y").message)
        self.assertEqual(calls, [])

        screen.handle_key("enter")
        screen.handle_key("enter")
        self.assertEqual(screen.handle_key("c").message, "Confirmation required before guided deployment execution.")
        self.assertEqual(screen.handle_key("y").message, "mysql.start completed successfully.")
        self.assertEqual(calls, ["mysql.start"])
        self.assertEqual(screen.snapshot.step_statuses[0], GuidedStepStatus.SUCCESS)
        self.assertIn("Result: mysql.start completed successfully.", screen.render())

    def test_resume_and_repair_are_represented_without_live_discovery(self) -> None:
        screen = GuidedDeploymentScreen()

        screen.handle_key("m")
        resume = screen.handle_key("2")
        self.assertEqual(resume.message, "Selected mode Resume deployment.")
        self.assertEqual(screen.snapshot.mode.id, "resume")

        screen.handle_key("m")
        repair = screen.handle_key("3")
        self.assertEqual(repair.message, "Selected mode Repair deployment.")
        self.assertEqual(screen.snapshot.mode.id, "repair")

    def test_completion_handoffs_target_existing_workflows(self) -> None:
        screen = GuidedDeploymentScreen(runner=lambda operation_id: _result(operation_id))
        statuses = [GuidedStepStatus.SUCCESS for _step in screen.snapshot.steps]
        statuses[-1] = GuidedStepStatus.READY
        screen.snapshot = screen.snapshot.__class__(
            phase=GuidedDeploymentPhase.STEPS,
            profile=screen.snapshot.profile,
            mode=screen.snapshot.mode,
            steps=screen.snapshot.steps,
            current_step_index=len(screen.snapshot.steps) - 1,
            step_statuses=tuple(statuses),
            message="final step",
        )

        screen.handle_key("c")
        self.assertEqual(screen.handle_key("y").message, "scancentral_dast.start completed successfully.")
        self.assertEqual(screen.snapshot.phase, GuidedDeploymentPhase.COMPLETE)
        self.assertEqual({handoff.workflow_target for handoff in COMPLETION_HANDOFFS}, {"diagnostics", "status", "logs", "help_center", "lifecycle"})

        handoff = screen.handle_key("2")
        self.assertEqual(handoff.open_target, "status")

    def test_deploy_menu_guided_item_dispatches_to_contract_screen(self) -> None:
        selected = find_item("deploy", "1")
        assert selected is not None

        result = workflows.dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertEqual(result.screen.id, "guided_deployment")
        self.assertIn("Guided deployment contract", result.screen.render())


if __name__ == "__main__":
    unittest.main()
