"""M9.7 guided deployment TUI workflow tests.

These tests define the implementation-facing contract for the Python guided
deployment workflow. They use injected profiles, steps, status providers, and
runners only; no Kubernetes, Helm, Docker, network, credentials, or live lab
state may be required.
"""

from __future__ import annotations

import unittest

from fortifylab.navigation import find_item
from fortifylab.operations import CommandExecutionResult, OperationRunResult
from fortifylab.tui.guided_deployment import (
    GuidedDeploymentMode,
    GuidedDeploymentProfile,
    GuidedDeploymentScreen,
    GuidedDeploymentStep,
    StepRuntimeState,
)
from fortifylab.tui.workflows import dispatch_menu_item


def _profiles() -> tuple[GuidedDeploymentProfile, ...]:
    return (
        GuidedDeploymentProfile("ssc_only", "SSC only", ("mysql", "postgresql", "ssc")),
        GuidedDeploymentProfile(
            "sast_full",
            "SAST full",
            ("mysql", "postgresql", "ssc", "lim", "scancentral_sast"),
        ),
        GuidedDeploymentProfile(
            "full_stack",
            "Full stack",
            (
                "mysql",
                "postgresql",
                "ssc",
                "lim",
                "scancentral_sast",
                "scancentral_dast",
                "juice_shop",
            ),
        ),
    )


def _modes() -> tuple[GuidedDeploymentMode, ...]:
    return (
        GuidedDeploymentMode("fresh", "Fresh deployment", resume_available=False, repair_available=False),
        GuidedDeploymentMode("resume", "Resume deployment", resume_available=True, repair_available=False),
        GuidedDeploymentMode("repair", "Repair selected step", resume_available=False, repair_available=True),
    )


def _steps(profile_id: str, mode_id: str) -> tuple[GuidedDeploymentStep, ...]:
    selected = next(profile for profile in _profiles() if profile.id == profile_id)
    state = StepRuntimeState.READY if mode_id == "fresh" else StepRuntimeState.UNAVAILABLE
    return tuple(
        GuidedDeploymentStep(
            step_id,
            step_id.replace("_", " ").title(),
            f"{step_id}.start",
            state,
            why="resume metadata is not available in this clone-safe fixture" if mode_id != "fresh" else "ready for preview",
        )
        for step_id in selected.step_ids
    )


def _run_result(operation_id: str, exit_code: int, *, stdout: str = "", stderr: str = "") -> OperationRunResult:
    return OperationRunResult(
        operation_id,
        exit_code,
        (
            CommandExecutionResult(
                ("bash", f"apps/{operation_id.replace('.', '/')}.sh"),
                exit_code,
                stdout,
                stderr,
                0.01,
            ),
        ),
    )


class M9GuidedDeploymentWorkflowTests(unittest.TestCase):
    def _screen(self, *, runner=None) -> GuidedDeploymentScreen:
        return GuidedDeploymentScreen(
            profiles=_profiles(),
            modes=_modes(),
            steps_provider=_steps,
            runner=runner or (lambda operation_id: _run_result(operation_id, 0, stdout="ok")),
        )

    def test_guided_deployment_dispatch_from_preserved_navigation_opens_workflow_screen(self) -> None:
        cases = (("deploy", "1"), ("more_tools", "1"))

        for menu_id, key in cases:
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None

                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertEqual(result.screen.id, "guided_deployment")
                self.assertEqual(result.screen.title, "Guided deployment")
                self.assertIn("Profile selection", result.screen.render())

    def test_profile_and_mode_selection_support_arrows_numbers_and_explicit_state(self) -> None:
        screen = self._screen()

        self.assertEqual(screen.stage, "profile_selection")
        self.assertEqual(screen.selected_profile_id, "ssc_only")
        self.assertEqual(screen.handle_key("down").message, "Selected profile SAST full.")
        self.assertEqual(screen.selected_profile_id, "sast_full")
        self.assertEqual(screen.handle_key("3").message, "Selected profile Full stack.")
        self.assertEqual(screen.selected_profile_id, "full_stack")

        self.assertEqual(screen.handle_key("enter").message, "Selected Full stack profile.")
        self.assertEqual(screen.stage, "deployment_mode_selection")
        self.assertIn("Deployment mode selection", screen.render())

        self.assertEqual(screen.handle_key("2").message, "Selected mode Resume deployment.")
        self.assertEqual(screen.selected_mode_id, "resume")
        self.assertEqual(screen.handle_key("enter").message, "Selected Resume deployment mode.")
        self.assertEqual(screen.stage, "step_controls")
        self.assertEqual(screen.selected_step_id, "mysql")
        self.assertIn("UNAVAILABLE MySQL", screen.render())
        self.assertIn("resume metadata is not available", screen.render())

    def test_step_controls_require_dry_run_and_confirmation_before_execution(self) -> None:
        calls: list[str] = []

        def runner(operation_id: str) -> OperationRunResult:
            calls.append(operation_id)
            return _run_result(operation_id, 0, stdout="started cleanly")

        screen = self._screen(runner=runner)
        screen.handle_key("2")
        screen.handle_key("enter")
        screen.handle_key("enter")

        self.assertEqual(screen.stage, "step_controls")
        self.assertEqual(screen.selected_step_id, "mysql")
        self.assertEqual(screen.handle_key("down").message, "Selected step PostgreSQL.")
        self.assertEqual(screen.handle_key("3").message, "Selected step SSC.")
        self.assertEqual(screen.selected_step_id, "ssc")

        self.assertIn("Previewed ssc.start", screen.handle_key("p").message)
        self.assertEqual(calls, [])
        assert screen.last_preview is not None
        self.assertEqual(screen.last_preview.operation_id, "ssc.start")
        self.assertTrue(screen.last_preview.confirmation_required)

        self.assertIn("Confirmation required", screen.handle_key("c").message)
        self.assertEqual(calls, [])
        self.assertEqual(screen.handle_key("n").message, "Guided deployment step cancelled.")
        self.assertEqual(calls, [])

        self.assertIn("Confirmation required", screen.handle_key("enter").message)
        self.assertEqual(screen.handle_key("y").message, "ssc.start completed successfully.")
        self.assertEqual(calls, ["ssc.start"])
        self.assertEqual(screen.step_state("ssc"), StepRuntimeState.COMPLETE)
        self.assertIn("COMPLETE SSC", screen.render())

    def test_unavailable_resume_or_repair_step_does_not_execute_runner(self) -> None:
        calls: list[str] = []
        screen = self._screen(runner=lambda operation_id: calls.append(operation_id) or _run_result(operation_id, 0))
        screen.handle_key("1")
        screen.handle_key("enter")
        screen.handle_key("2")
        screen.handle_key("enter")

        self.assertEqual(screen.stage, "step_controls")
        self.assertEqual(screen.step_state("mysql"), StepRuntimeState.UNAVAILABLE)
        self.assertIn("unavailable", screen.handle_key("p").message.lower())
        self.assertIn("unavailable", screen.handle_key("c").message.lower())
        self.assertIn("unavailable", screen.handle_key("y").message.lower())
        self.assertEqual(calls, [])

    def test_progress_and_results_are_redacted_before_display(self) -> None:
        def runner(operation_id: str) -> OperationRunResult:
            return _run_result(
                operation_id,
                1,
                stdout="password=hunter2\nAuthorization: Bearer abc.def\n",
                stderr="token=secret-token\nsee /home/tre/.ssh/github-treisland-agent\n",
            )

        screen = self._screen(runner=runner)
        screen.handle_key("1")
        screen.handle_key("enter")
        screen.handle_key("enter")
        screen.handle_key("p")
        screen.handle_key("c")
        self.assertEqual(screen.handle_key("y").message, "mysql.start failed with exit code 1.")

        rendered = screen.render()
        self.assertIn("password=<redacted>", rendered)
        self.assertIn("Authorization: Bearer <redacted>", rendered)
        self.assertIn("token=<redacted>", rendered)
        self.assertIn("<sensitive-path>", rendered)
        self.assertNotIn("hunter2", rendered)
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("/home/tre/.ssh/github-treisland-agent", rendered)

    def test_completion_handoffs_link_to_existing_workflows(self) -> None:
        screen = self._screen()
        screen.handle_key("1")
        screen.handle_key("enter")
        screen.handle_key("enter")
        screen.mark_all_steps_complete()

        self.assertEqual(screen.stage, "completion_handoff")
        rendered = screen.render()
        for label in ("Diagnostics", "Status", "Logs", "Help", "Lifecycle"):
            self.assertIn(label, rendered)

        expected_targets = {
            "1": "diagnostics",
            "2": "status",
            "3": "logs",
            "4": "help_center",
            "5": "lifecycle",
        }
        for key, target in expected_targets.items():
            with self.subTest(key=key):
                result = screen.handle_key(key)
                self.assertIn("Open", result.message)
                self.assertEqual(result.open_target, target)

    def test_refresh_back_and_quit_are_screen_level_contracts(self) -> None:
        screen = self._screen()

        self.assertEqual(screen.handle_key("r").message, "Refreshed guided deployment workflow.")
        self.assertTrue(screen.handle_key("b").exit_screen)
        self.assertTrue(screen.handle_key("q").exit_screen)


if __name__ == "__main__":
    unittest.main()
