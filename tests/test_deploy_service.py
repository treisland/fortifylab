"""Unit tests for fortifylab.services.deploy_service (M3 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.orchestration import OperationController, RetryPolicy, StepStatus  # noqa: E402
from fortifylab.services.deploy_service import DeployService, adapter_step_ids  # noqa: E402


class DeployServiceTests(unittest.TestCase):
    def test_ssc_only_plan_is_certs_secrets_mysql_ssc_in_dependency_order(self) -> None:
        service = DeployService("ssc_only")
        step_ids = service.plan.step_ids()
        self.assertEqual(service.plan.validate(), ())
        self.assertIn("certs", step_ids)
        self.assertIn("ssc", step_ids)
        # dashboard/secrets both depend on certs; mysql depends on secrets; ssc depends on mysql.
        self.assertLess(step_ids.index("certs"), step_ids.index("secrets"))
        self.assertLess(step_ids.index("secrets"), step_ids.index("mysql"))
        self.assertLess(step_ids.index("mysql"), step_ids.index("ssc"))

    def test_plan_excludes_steps_the_adapter_does_not_know_yet(self) -> None:
        # prereqs/inputs/preflight/configure are part of the guided profile
        # but have no Bash adapter entry yet -- they must not appear in the
        # plan the deploy service actually drives.
        service = DeployService("ssc_only")
        for excluded in ("prereqs", "inputs", "preflight", "configure"):
            self.assertNotIn(excluded, service.plan.step_ids())

    def test_runnable_steps_starts_with_only_the_no_dependency_step(self) -> None:
        service = DeployService("ssc_only")
        runnable = service.runnable_steps()
        self.assertEqual([step.step_id for step in runnable], ["certs"])

    def test_dry_run_preview_does_not_advance_the_plan(self) -> None:
        service = DeployService("ssc_only")
        result = service.run_next(execute=False)
        self.assertEqual(result.step_id, "certs")
        self.assertEqual(result.status, StepStatus.READY)
        self.assertIn("not executed", result.detail)
        # Still PENDING and still the only runnable step -- preview is repeatable.
        self.assertEqual(service.states["certs"].status, StepStatus.PENDING)
        self.assertEqual([step.step_id for step in service.runnable_steps()], ["certs"])

        second_preview = service.run_next(execute=False)
        self.assertEqual(second_preview.step_id, "certs")

    def test_execute_advances_the_plan_and_unlocks_dependents(self) -> None:
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)

        # "true" always succeeds; stand in for the real cert script so this
        # test doesn't touch a real cluster.
        service.plan.steps[0].command  # sanity: DeploymentStep is what we think
        object.__setattr__(service.plan.steps[0], "command", ("true",))

        result = service.run_next(execute=True)
        self.assertEqual(result.status, StepStatus.COMPLETE)
        self.assertEqual(service.states["certs"].status, StepStatus.COMPLETE)
        self.assertEqual(service.session.states["certs"].status, StepStatus.COMPLETE)

        runnable_next = {step.step_id for step in service.runnable_steps()}
        # dashboard and secrets both only depend on certs, now complete.
        self.assertIn("secrets", runnable_next)
        self.assertNotIn("certs", runnable_next)

    def test_execute_records_failure_without_crashing(self) -> None:
        controller = OperationController(RetryPolicy(max_attempts=1))
        service = DeployService("ssc_only", controller=controller)
        object.__setattr__(service.plan.steps[0], "command", ("false",))

        result = service.run_next(execute=True)
        self.assertEqual(result.status, StepStatus.FAILED)
        self.assertEqual(service.states["certs"].status, StepStatus.FAILED)
        self.assertTrue(service.has_failed)
        self.assertFalse(service.is_complete)

    def test_run_next_returns_none_when_nothing_is_runnable(self) -> None:
        service = DeployService("ssc_only")
        for step in service.plan.steps:
            service.states[step.step_id] = service.states[step.step_id].__class__(
                step_id=step.step_id, status=StepStatus.COMPLETE
            )
        self.assertIsNone(service.run_next(execute=True))
        self.assertTrue(service.is_complete)

    def test_adapter_step_ids_matches_the_bash_adapter_script_table(self) -> None:
        ids = adapter_step_ids()
        self.assertIn("ssc", ids)
        self.assertIn("certs", ids)
        self.assertNotIn("prereqs", ids)


if __name__ == "__main__":
    unittest.main()
