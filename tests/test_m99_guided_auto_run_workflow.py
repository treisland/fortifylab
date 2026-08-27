"""M9.9.2 functional guided deployment TUI tests.

These tests define the fixture-only contract for turning Guided Deployment into
an auto-running Python TUI workflow. They must not invoke Kubernetes, Helm,
Docker, network, credentials, real deployment scripts, or live lab state.
"""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import patch

from fortifylab.operations import CommandExecutionResult, OperationRunResult


REQUIRED_CONTRACT = (
    "GuidedDeploymentScreen",
    "GuidedDeploymentProfile",
    "GuidedReleaseFamily",
    "GuidedDeploymentPlan",
    "GuidedDeploymentPlanStep",
    "GuidedDeploymentRunEvent",
    "GuidedDeploymentRunStatus",
    "StepRuntimeState",
    "build_guided_deployment_plan",
)


def _contract():
    try:
        module = importlib.import_module("fortifylab.tui.guided_deployment")
    except Exception as exc:  # pragma: no cover - exercised only while contract is missing/broken.
        raise AssertionError(f"M9.9.2 guided deployment auto-run contract could not import: {exc}") from exc
    missing = [name for name in REQUIRED_CONTRACT if not hasattr(module, name)]
    if missing:
        raise AssertionError(
            "M9.9.2 guided deployment auto-run contract is missing: "
            + ", ".join(missing)
        )
    return module


def _profiles(contract):
    return (
        contract.GuidedDeploymentProfile(
            "ssc_only",
            "SSC only",
            "MySQL, PostgreSQL, and SSC.",
            ("mysql", "postgresql", "ssc"),
        ),
        contract.GuidedDeploymentProfile(
            "sast_full",
            "SAST full",
            "SSC, LIM, ScanCentral SAST, and Juice Shop.",
            ("mysql", "postgresql", "ssc", "lim", "scancentral_sast", "juice_shop"),
        ),
    )


def _release_families(contract):
    return (
        contract.GuidedReleaseFamily(
            "23.2",
            "Fortify 23.2",
            "Pinned Fortify 23.2 chart and image family.",
            {"SSC_VERSION": "23.2.0", "SCSAST_VERSION": "23.2.0"},
        ),
        contract.GuidedReleaseFamily(
            "24.4",
            "Fortify 24.4",
            "Pinned Fortify 24.4 chart and image family.",
            {"SSC_VERSION": "24.4.0", "SCSAST_VERSION": "24.4.0"},
        ),
    )


def _plan_builder(contract):
    def build(profile, release_family):
        steps = tuple(
            contract.GuidedDeploymentPlanStep(
                step_id=step_id,
                label=step_id.replace("_", " ").title(),
                component=step_id,
                operation_id=f"{step_id}.start",
                commands=(f"bash apps/{step_id}/start.sh --family {release_family.id}",),
                summary=f"Deploy {step_id} from {release_family.label}.",
            )
            for step_id in profile.step_ids
        )
        return contract.GuidedDeploymentPlan(profile=profile, release_family=release_family, steps=steps)

    return build


class FakeGuidedRunner:
    def __init__(self, contract, *, fail_step: str | None = None) -> None:
        self.contract = contract
        self.fail_step = fail_step
        self.calls: list[str] = []

    def __call__(self, plan):
        for step in plan.steps:
            self.calls.append(step.operation_id)
            yield self.contract.GuidedDeploymentRunEvent(
                step_id=step.step_id,
                component=step.component,
                operation=step.operation_id,
                status=self.contract.GuidedDeploymentRunStatus.RUNNING,
                message=f"{step.label} running",
                stdout=f"starting {step.operation_id}\npassword=super-secret\n",
                stderr="",
                duration_seconds=0.1,
            )
            if step.step_id == self.fail_step:
                yield self.contract.GuidedDeploymentRunEvent(
                    step_id=step.step_id,
                    component=step.component,
                    operation=step.operation_id,
                    status=self.contract.GuidedDeploymentRunStatus.FAILED,
                    message=f"{step.label} failed",
                    stdout="",
                    stderr="token=bad-secret\n",
                    duration_seconds=0.2,
                )
                return
            yield self.contract.GuidedDeploymentRunEvent(
                step_id=step.step_id,
                component=step.component,
                operation=step.operation_id,
                status=self.contract.GuidedDeploymentRunStatus.INSTALLED,
                message=f"{step.label} installed",
                stdout=f"{step.component} ready\n",
                stderr="",
                duration_seconds=0.3,
            )


class M99GuidedAutoRunWorkflowTests(unittest.TestCase):
    def _screen(self, *, runner: FakeGuidedRunner | None = None, log_limit: int = 4):
        contract = _contract()
        active_runner = runner or FakeGuidedRunner(contract)
        screen = contract.GuidedDeploymentScreen(
            profiles=_profiles(contract),
            release_families=_release_families(contract),
            plan_builder=_plan_builder(contract),
            runner=active_runner,
            log_limit=log_limit,
        )
        return contract, active_runner, screen

    def _choose_sast_full_244(self, screen) -> None:
        self.assertEqual(screen.handle_key("2").message, "Selected profile SAST full.")
        self.assertEqual(screen.handle_key("enter").message, "Selected SAST full profile.")
        self.assertEqual(screen.handle_key("2").message, "Selected Flight Plan Fortify 24.4.")
        self.assertEqual(screen.handle_key("enter").message, "Prepared deployment plan for SAST full on Fortify 24.4.")

    def test_profile_release_family_selection_and_plan_preview_use_arrows_and_numbers(self) -> None:
        _contract_obj, runner, screen = self._screen()

        self.assertEqual(screen.stage, "profile_selection")
        self.assertEqual(screen.selected_profile_id, "ssc_only")
        self.assertEqual(screen.handle_key("down").message, "Selected profile SAST full.")
        self.assertEqual(screen.selected_profile_id, "sast_full")
        self.assertEqual(screen.handle_key("enter").message, "Selected SAST full profile.")

        self.assertEqual(screen.stage, "release_family_selection")
        rendered = screen.render()
        self.assertIn("Flight Plan selection", rendered)
        self.assertEqual(screen.handle_key("2").message, "Selected Flight Plan Fortify 24.4.")
        self.assertEqual(screen.selected_release_family_id, "24.4")
        self.assertEqual(screen.handle_key("enter").message, "Prepared deployment plan for SAST full on Fortify 24.4.")

        rendered = screen.render()
        self.assertEqual(screen.stage, "plan_preview")
        self.assertIn("Plan preview", rendered)
        self.assertIn("ScanCentral SAST", rendered)
        self.assertNotIn("bash apps/scancentral_sast/start.sh --family 24.4", rendered)
        self.assertIn("Continue: press c", rendered)
        self.assertIn("Inspect: press i", rendered)
        self.assertIn("will auto-run the deployment", rendered)
        self.assertEqual(runner.calls, [])

    def test_continue_prompt_requires_uppercase_deploy_and_cancel_executes_nothing(self) -> None:
        _contract_obj, runner, screen = self._screen()
        self._choose_sast_full_244(screen)

        result = screen.handle_key("c")
        self.assertEqual(result.message, "Type DEPLOY to start automatic deployment.")
        self.assertEqual(screen.stage, "deployment_confirmation")
        self.assertIn("If you proceed, FortifyLab will automatically run", screen.render())

        self.assertIn("Type DEPLOY", screen.handle_key("deploy").message)
        self.assertEqual(runner.calls, [])
        self.assertEqual(screen.handle_key("n").message, "Guided deployment cancelled before execution.")
        self.assertEqual(screen.stage, "cancelled")
        self.assertEqual(runner.calls, [])

    def test_deploy_confirmation_autoruns_fake_runner_and_updates_colored_status_table(self) -> None:
        contract, runner, screen = self._screen()
        self._choose_sast_full_244(screen)
        screen.handle_key("c")

        self.assertEqual(screen.handle_key("DEPLOY").message, "Guided deployment auto-run completed.")
        self.assertEqual(runner.calls[0:3], ["mysql.start", "postgresql.start", "ssc.start"])
        self.assertEqual(screen.stage, "deployment_complete")

        rows = {row.component: row for row in screen.status_rows}
        self.assertEqual(rows["mysql"].status, contract.GuidedDeploymentRunStatus.INSTALLED)
        self.assertEqual(rows["ssc"].status, contract.GuidedDeploymentRunStatus.INSTALLED)
        self.assertEqual(rows["juice_shop"].status, contract.GuidedDeploymentRunStatus.INSTALLED)

        rendered = screen.render_status_table()
        self.assertIn("Component", rendered)
        self.assertIn("Operation", rendered)
        self.assertIn("Status", rendered)
        self.assertIn("mysql", rendered)
        self.assertIn("installed", rendered.lower())
        self.assertIn("[green]", rendered)
        self.assertIn("Success: guided deployment complete.", screen.render())

    def test_logs_are_bounded_and_redacted_and_can_be_opened_from_deployment_view(self) -> None:
        _contract_obj, _runner, screen = self._screen(log_limit=3)
        self._choose_sast_full_244(screen)
        screen.handle_key("c")
        screen.handle_key("DEPLOY")

        logs = screen.deployment_logs
        self.assertLessEqual(len(logs), 3)
        rendered_logs = screen.render_logs()
        self.assertIn("Deployment logs", rendered_logs)
        self.assertIn("<redacted>", rendered_logs)
        self.assertNotIn("super-secret", rendered_logs)
        self.assertNotIn("bad-secret", rendered_logs)

        log_result = screen.handle_key("l")
        self.assertEqual(log_result.message, "Opened deployment logs.")
        self.assertEqual(screen.stage, "deployment_logs")
        self.assertIn("Deployment logs", screen.render())

    def test_inspection_view_shows_plan_adapter_and_current_step_without_credentials(self) -> None:
        _contract_obj, _runner, screen = self._screen()
        self._choose_sast_full_244(screen)

        inspection = screen.render_inspection()
        self.assertIn("Inspection", inspection)
        self.assertIn("Profile: SAST full", inspection)
        self.assertIn("Flight Plan: Fortify 24.4", inspection)
        self.assertIn("Adapter: mysql.start", inspection)
        self.assertIn("bash apps/mysql/start.sh --family 24.4", inspection)
        self.assertNotIn("password=", inspection)
        self.assertNotIn("token=", inspection)

        inspect_result = screen.handle_key("i")
        self.assertEqual(inspect_result.message, "Opened deployment inspection.")
        self.assertEqual(screen.stage, "deployment_inspection")

    def test_failure_stops_auto_run_marks_remaining_steps_pending_and_exposes_handoffs(self) -> None:
        contract = _contract()
        runner = FakeGuidedRunner(contract, fail_step="ssc")
        _contract_obj, active_runner, screen = self._screen(runner=runner)
        self._choose_sast_full_244(screen)
        screen.handle_key("c")

        self.assertEqual(screen.handle_key("DEPLOY").message, "Guided deployment stopped after SSC failed.")
        self.assertIs(active_runner, runner)
        self.assertEqual(active_runner.calls, ["mysql.start", "postgresql.start", "ssc.start"])
        self.assertEqual(screen.stage, "deployment_failed")

        rows = {row.component: row for row in screen.status_rows}
        self.assertEqual(rows["ssc"].status, contract.GuidedDeploymentRunStatus.FAILED)
        self.assertEqual(rows["lim"].status, contract.GuidedDeploymentRunStatus.PENDING)
        self.assertEqual(rows["scancentral_sast"].status, contract.GuidedDeploymentRunStatus.PENDING)

        rendered = screen.render()
        self.assertIn("Logs", rendered)
        self.assertIn("Inspection", rendered)
        self.assertIn("Diagnostics", rendered)
        self.assertEqual(screen.handle_key("1").open_target, "logs")
        self.assertEqual(screen.handle_key("2").open_target, "diagnostics")
        self.assertEqual(screen.handle_key("3").open_target, "status")


    def test_default_workflow_uses_release_family_path_for_python_tui(self) -> None:
        contract = _contract()

        screen = contract.build_guided_deployment_workflow()

        self.assertEqual(screen.stage, "profile_selection")
        self.assertIn("Profile selection", screen.render())
        self.assertIn("Selected", screen.handle_key("enter").message)
        self.assertEqual(screen.stage, "release_family_selection")
        rendered = screen.render()
        self.assertIn("Flight Plan selection", rendered)
        self.assertIn("Fortify 26.2", rendered)
        self.assertNotIn("Current recommended", rendered)

    def test_real_guided_runner_delegates_to_operation_runner_after_confirmation(self) -> None:
        contract = _contract()
        profile = contract.GuidedDeploymentProfile("one", "One", "One step", ("mysql",))
        family = contract.GuidedReleaseFamily("26.2", "Fortify 26.2", "Recommended", "fortify-26.2")
        plan = contract.GuidedDeploymentPlan(
            profile=profile,
            release_family=family,
            steps=(
                contract.GuidedDeploymentPlanStep(
                    step_id="mysql",
                    label="MySQL",
                    component="mysql",
                    operation_id="mysql.start",
                    commands=("bash apps/mysql/start.sh",),
                ),
            ),
        )
        operation_result = OperationRunResult(
            "mysql.start",
            0,
            (CommandExecutionResult(("bash", "apps/mysql/start.sh"), 0, "mysql ready\n", "", 0.2),),
        )

        with patch("fortifylab.tui.guided_deployment.run_operation", return_value=operation_result) as run_operation:
            events = list(contract._real_guided_plan_runner(plan))

        run_operation.assert_called_once_with("mysql.start", confirmed=True)
        self.assertEqual(events[0].status, contract.GuidedDeploymentRunStatus.RUNNING)
        self.assertEqual(events[-1].status, contract.GuidedDeploymentRunStatus.INSTALLED)
        self.assertIn("mysql ready", events[-1].stdout)

    def test_plan_builder_function_is_fixture_only_and_contains_selected_profile_family(self) -> None:
        contract = _contract()
        profile = _profiles(contract)[1]
        release_family = _release_families(contract)[0]

        plan = contract.build_guided_deployment_plan(
            profile,
            release_family,
            plan_builder=_plan_builder(contract),
        )

        self.assertEqual(plan.profile.id, "sast_full")
        self.assertEqual(plan.release_family.id, "23.2")
        self.assertEqual([step.step_id for step in plan.steps], list(profile.step_ids))
        self.assertTrue(all(step.operation_id.endswith(".start") for step in plan.steps))
        self.assertTrue(all("--family 23.2" in step.commands[0] for step in plan.steps))


if __name__ == "__main__":
    unittest.main()
