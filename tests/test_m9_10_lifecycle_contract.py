"""M9.10 lifecycle parity contract tests.

These tests pin Bash-style lifecycle behavior for the Python TUI without running
Kubernetes, Helm, Docker, network calls, or repository lifecycle scripts.
"""

from __future__ import annotations

import unittest

from fortifylab.tui.lifecycle import (
    build_lifecycle_plan,
    build_lifecycle_scope,
    lifecycle_action_options,
    lifecycle_completion_handoffs,
)


class M910LifecycleParityContractTests(unittest.TestCase):
    def test_lifecycle_actions_are_user_facing_and_safety_aware(self) -> None:
        actions = {action.id: action for action in lifecycle_action_options()}

        self.assertEqual(actions["start"].label, "Start / upgrade")
        self.assertEqual(actions["stop"].data_impact, "retained")
        self.assertIn("preserving persistent data", actions["stop"].description)
        self.assertTrue(actions["destroy"].destructive)
        self.assertEqual(actions["destroy"].data_impact, "deleted")
        self.assertIn("deletes data", actions["destroy"].label)

        self.assertFalse(actions["restart"].available)
        self.assertIn("ordered stop/start", actions["restart"].unavailable_reason or "")
        self.assertFalse(actions["repair"].available)
        self.assertFalse(actions["reset"].available)

    def test_all_lab_start_runs_forward_dependency_order(self) -> None:
        plan = build_lifecycle_plan("lifecycle.start_lab", "start")

        self.assertEqual(plan.scope.label, "All lab deployments")
        self.assertEqual(
            plan.operation_ids,
            (
                "mysql.start",
                "postgresql.start",
                "ssc.start",
                "lim.start",
                "scancentral_sast.start",
                "scancentral_dast.start",
            ),
        )
        self.assertEqual(plan.data_impact, "retained")
        self.assertFalse(plan.destructive)
        self.assertIn("dependency order", plan.order_note)

    def test_all_lab_stop_runs_reverse_order_and_preserves_data(self) -> None:
        plan = build_lifecycle_plan("lifecycle.stop_lab", "stop")

        self.assertEqual(
            plan.operation_ids,
            (
                "scancentral_dast.stop",
                "scancentral_sast.stop",
                "lim.stop",
                "ssc.stop",
                "postgresql.stop",
                "mysql.stop",
            ),
        )
        self.assertEqual(plan.data_impact, "retained")
        self.assertFalse(plan.destructive)
        self.assertIn("reverse dependency order", plan.order_note)

    def test_full_lab_destroy_requires_full_lab_phrase_and_reverse_order(self) -> None:
        plan = build_lifecycle_plan("lifecycle.reset_lab", "destroy")

        self.assertTrue(plan.destructive)
        self.assertEqual(plan.data_impact, "deleted")
        self.assertEqual(plan.confirmation_phrase, "DESTROY FORTIFY LAB")
        self.assertEqual(
            plan.operation_ids,
            (
                "scancentral_dast.destroy",
                "scancentral_sast.destroy",
                "lim.destroy",
                "ssc.destroy",
                "postgresql.destroy",
                "mysql.destroy",
            ),
        )

    def test_selected_profile_scope_limits_start_and_stop_plans(self) -> None:
        start_plan = build_lifecycle_plan("lifecycle.start_lab", "start", profile_id="ssc_only")
        stop_plan = build_lifecycle_plan("lifecycle.stop_lab", "stop", profile_id="ssc_only")

        self.assertEqual(start_plan.scope.profile_id, "ssc_only")
        self.assertEqual(start_plan.operation_ids, ("mysql.start", "ssc.start"))
        self.assertEqual(stop_plan.operation_ids, ("ssc.stop", "mysql.stop"))
        self.assertNotIn("postgresql.start", start_plan.operation_ids)
        self.assertNotIn("scancentral_sast.stop", stop_plan.operation_ids)

    def test_selected_profile_destroy_has_distinct_confirmation_phrase(self) -> None:
        plan = build_lifecycle_plan("lifecycle.reset_lab", "destroy", profile_id="sast_full")

        self.assertTrue(plan.destructive)
        self.assertEqual(plan.confirmation_phrase, "DESTROY SELECTED PROFILE")
        self.assertEqual(plan.scope.label, "Selected profile: SAST Full Lab")
        self.assertEqual(plan.operation_ids[0], "juice_shop.destroy")
        self.assertEqual(plan.operation_ids[-1], "mysql.destroy")

    def test_component_and_sample_scopes_stay_isolated(self) -> None:
        component = build_lifecycle_plan("app_lifecycle.ssc", "destroy")
        sample = build_lifecycle_plan("sample_apps.webgoat", "stop")

        self.assertEqual(component.scope.component_ids, ("ssc",))
        self.assertEqual(component.operation_ids, ("ssc.destroy",))
        self.assertEqual(component.confirmation_phrase, "DESTROY")
        self.assertEqual(sample.scope.component_ids, ("webgoat",))
        self.assertEqual(sample.operation_ids, ("webgoat.stop",))
        self.assertEqual(sample.data_impact, "retained")

    def test_completion_handoffs_include_bash_style_operator_paths(self) -> None:
        handoffs = {handoff.key: handoff.workflow_target for handoff in lifecycle_completion_handoffs()}

        self.assertEqual(handoffs["1"], "logs")
        self.assertEqual(handoffs["2"], "diagnostics")
        self.assertEqual(handoffs["3"], "status")
        self.assertEqual(handoffs["i"], "inspection")
        self.assertEqual(handoffs["m"], "main")

    def test_unknown_profile_and_deferred_actions_are_safe(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown lifecycle profile"):
            build_lifecycle_scope("lifecycle.start_lab", profile_id="missing")

        with self.assertRaisesRegex(ValueError, "Repair needs"):
            build_lifecycle_plan("lifecycle.start_lab", "repair")


if __name__ == "__main__":
    unittest.main()
