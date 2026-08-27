"""M9.9.1 guided deployment plan contract tests.

These tests keep the functional guided deployment contract clone-safe. They prove
profile and release-family selections produce a concrete plan, status/log and
inspection models are available, and auto-run remains behind an explicit DEPLOY
gate without invoking Kubernetes, Helm, Docker, network, scripts, or credentials.
"""

from __future__ import annotations

import unittest

from fortifylab.tui.guided_deployment import (
    DeploymentLogBuffer,
    DeploymentLogEvent,
    DeploymentStatusColor,
    GuidedDeploymentMode,
    GuidedDeploymentProfile,
    GuidedDeploymentStep,
    ReleaseFamily,
    StepRuntimeState,
    build_deployment_inspection,
    build_deployment_plan,
    build_deployment_status_rows,
    build_guided_run_contract,
    release_family,
)


PROFILES = (
    GuidedDeploymentProfile("ssc_only", "SSC only", "SSC with database dependencies.", ("mysql", "postgresql", "ssc")),
    GuidedDeploymentProfile("sast_lab", "SAST lab", "SSC, LIM, ScanCentral SAST, and Juice Shop.", ("mysql", "postgresql", "ssc", "lim", "scancentral_sast", "juice_shop"), sample=True),
)

FAMILIES = (
    ReleaseFamily("24x", "Fortify 24.x", "Pinned 24.x lab family.", "24.x", ("FORTIFY_FLIGHT_PLAN", "FORTIFY_SSC_CHART_VERSION")),
    ReleaseFamily("25x", "Fortify 25.x", "Pinned 25.x lab family.", "25.x", ("FORTIFY_FLIGHT_PLAN", "FORTIFY_SSC_IMAGE_TAG"), recommended=True),
)

MODES = (GuidedDeploymentMode("fresh", "Fresh deployment", "Auto-run selected plan from the beginning."),)


def steps_provider(profile_id: str, mode_id: str) -> tuple[GuidedDeploymentStep, ...]:
    del mode_id
    profile = next(profile for profile in PROFILES if profile.id == profile_id)
    return tuple(GuidedDeploymentStep(step_id, step_id, f"{step_id}.start", "ready") for step_id in profile.step_ids)


class M99GuidedDeploymentPlanContractTests(unittest.TestCase):
    def test_profile_and_release_family_build_concrete_operation_plan(self) -> None:
        plan = build_deployment_plan(
            profile_id="sast_lab",
            release_family_id="25x",
            mode_id="fresh",
            profiles=PROFILES,
            families=FAMILIES,
            modes=MODES,
            steps_provider=steps_provider,
        )

        self.assertEqual(plan.profile.id, "sast_lab")
        self.assertEqual(plan.release_family.flight_plan, "25.x")
        self.assertEqual(plan.mode.id, "fresh")
        self.assertEqual(
            plan.operation_ids,
            ("mysql.start", "postgresql.start", "ssc.start", "lim.start", "scancentral_sast.start", "juice_shop.start"),
        )
        self.assertGreaterEqual(plan.command_count, len(plan.steps))
        self.assertIn("automatically run", plan.continue_prompt)
        self.assertEqual(plan.confirmation_phrase, "DEPLOY")
        self.assertTrue(all(step.confirmation_required for step in plan.steps))
        self.assertIn("FORTIFY_SSC_IMAGE_TAG", plan.release_family.version_keys)

    def test_run_contract_starts_awaiting_deploy_confirmation_with_queued_status_rows(self) -> None:
        plan = build_deployment_plan(
            profile_id="ssc_only",
            release_family_id="24x",
            profiles=PROFILES,
            families=FAMILIES,
            modes=MODES,
            steps_provider=steps_provider,
        )

        contract = build_guided_run_contract(plan, current_step_id="ssc", log_limit=2)

        self.assertTrue(contract.awaiting_deploy_confirmation)
        self.assertEqual(contract.confirmation_note, "Type DEPLOY to auto-run the planned deployment steps.")
        self.assertEqual([row.component for row in contract.status_rows], ["MySQL", "PostgreSQL", "SSC"])
        self.assertTrue(all(row.state is StepRuntimeState.PENDING for row in contract.status_rows))
        self.assertTrue(all(row.color is DeploymentStatusColor.DIM for row in contract.status_rows))
        self.assertIsNotNone(contract.inspection)
        assert contract.inspection is not None
        self.assertEqual(contract.inspection.current_step_id, "ssc")
        self.assertEqual(contract.inspection.adapter_id, "ssc.start")
        self.assertIn("bash apps/ssc/start.sh", contract.inspection.command_preview)

    def test_status_rows_cover_expected_color_states(self) -> None:
        rows = build_deployment_status_rows(
            build_deployment_plan(
                profile_id="ssc_only",
                release_family_id="24x",
                profiles=PROFILES,
                families=FAMILIES,
                modes=MODES,
                steps_provider=steps_provider,
            )
        )
        running = rows[0].__class__("mysql", "mysql.start", StepRuntimeState.RUNNING, "00:02", "installing")
        installed = rows[1].__class__("ssc", "ssc.start", StepRuntimeState.COMPLETE, "01:20", "ready")
        failed = rows[2].__class__("scsast", "scancentral_sast.start", StepRuntimeState.FAILED, "--", "pending probe failed")

        self.assertEqual(running.color, DeploymentStatusColor.CYAN)
        self.assertEqual(installed.color, DeploymentStatusColor.GREEN)
        self.assertEqual(failed.color, DeploymentStatusColor.RED)

    def test_bounded_logs_are_redacted_before_rendering(self) -> None:
        logs = DeploymentLogBuffer(limit=2)
        logs = logs.append(DeploymentLogEvent("mysql", "system", "starting"))
        logs = logs.append(DeploymentLogEvent("ssc", "stdout", "password=hunter2"))
        logs = logs.append(DeploymentLogEvent("ssc", "stderr", "Authorization: Bearer abc.def"))

        rendered = "\n".join(logs.render())

        self.assertNotIn("starting", rendered)
        self.assertIn("password=<redacted>", rendered)
        self.assertIn("Authorization: <redacted>", rendered)
        self.assertNotIn("hunter2", rendered)
        self.assertNotIn("abc.def", rendered)

    def test_inspection_includes_adapter_commands_config_inputs_and_clone_safe_notes(self) -> None:
        plan = build_deployment_plan(
            profile_id="sast_lab",
            release_family_id="25x",
            profiles=PROFILES,
            families=FAMILIES,
            modes=MODES,
            steps_provider=steps_provider,
        )

        inspection = build_deployment_inspection(plan, current_step_id="scancentral_sast")

        self.assertEqual(inspection.profile_id, "sast_lab")
        self.assertEqual(inspection.release_family_id, "25x")
        self.assertEqual(inspection.adapter_id, "scancentral_sast.start")
        self.assertIn("bash apps/scsast/start.sh", inspection.command_preview)
        self.assertIn("FORTIFY_SSC_IMAGE_TAG", inspection.config_keys)
        self.assertIn("FORTIFY_SCSAST_CHART_VERSION", inspection.config_keys)
        self.assertTrue(any("Clone-safe" in note for note in inspection.notes))

    def test_release_family_lookup_is_stable_and_errors_for_unknown_ids(self) -> None:
        self.assertEqual(release_family("25x", families=FAMILIES).label, "Fortify 25.x")
        with self.assertRaises(KeyError):
            release_family("does-not-exist", families=FAMILIES)


if __name__ == "__main__":
    unittest.main()
