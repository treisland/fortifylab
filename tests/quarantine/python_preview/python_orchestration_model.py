"""Contracts for the Phase 3.3 Python deployment orchestration model."""

from __future__ import annotations

import unittest
from pathlib import Path

from fortifylab.orchestration import (
    BashOperationAdapter,
    DeploymentPlan,
    DeploymentStep,
    GuidedSession,
    OperationController,
    OperationState,
    RetryPolicy,
    StepStatus,
)


class DeploymentOrchestrationModelTests(unittest.TestCase):
    def test_plan_validates_dependencies_and_runnable_steps(self) -> None:
        plan = DeploymentPlan(
            name="demo",
            steps=(
                DeploymentStep("secrets", "Secrets", ("create-secrets",)),
                DeploymentStep("mysql", "MySQL", ("mysql",), dependencies=("secrets",)),
            ),
        )

        self.assertEqual(plan.validate(), ())
        runnable = plan.runnable_steps({"secrets": OperationState("secrets", StepStatus.COMPLETE)})
        self.assertEqual([step.step_id for step in runnable], ["mysql"])

    def test_session_records_resumable_step_metadata_without_secrets(self) -> None:
        session = GuidedSession("session-1", "full_lab", "mysql", auto_advance=True)
        updated = session.mark("mysql", StepStatus.FAILED, "Pod is still starting.")
        record = updated.to_record()

        self.assertEqual(record["current_step"], "mysql")
        self.assertTrue(record["auto_advance"])
        self.assertEqual(record["states"]["mysql"]["status"], "failed")
        self.assertNotIn("secret", str(record).lower())

    def test_operation_controller_dry_run_does_not_execute_command(self) -> None:
        controller = OperationController(RetryPolicy(max_attempts=3))
        step = DeploymentStep("ssc", "SSC", ("definitely-not-a-real-command",))

        result = controller.run(step, dry_run=True)

        self.assertEqual(result.status, StepStatus.READY)
        self.assertEqual(result.attempts, 0)
        self.assertIn("not executed", result.detail)

    def test_cancelled_controller_returns_cancelled_result(self) -> None:
        controller = OperationController()
        controller.cancel()

        result = controller.run(DeploymentStep("lim", "LIM", ("lim",)))

        self.assertEqual(result.status, StepStatus.CANCELLED)
        self.assertEqual(result.attempts, 0)

    def test_bash_adapter_maps_steps_to_existing_script_paths(self) -> None:
        adapter = BashOperationAdapter(Path("/repo"))
        plan = adapter.build_plan("ssc-only", ("certs", "secrets", "mysql", "ssc"))

        self.assertEqual(plan.validate(), ())
        self.assertEqual(plan.steps[3].command, ("/repo/apps/ssc/start.sh",))
        self.assertEqual(plan.steps[3].dependencies, ("mysql",))


if __name__ == "__main__":
    unittest.main()
