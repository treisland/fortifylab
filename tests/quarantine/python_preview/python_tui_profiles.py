"""Contracts for Python guided deployment profile planning."""

from __future__ import annotations

import unittest

from fortifylab.tui.profiles import build_profile, expand_components, profile_components_for


class GuidedProfileTests(unittest.TestCase):
    def test_ssc_only_expands_platform_database_and_ssc_steps(self) -> None:
        profile = build_profile("ssc_only")
        step_ids = [step.step_id for step in profile.steps]

        self.assertIn("preflight", step_ids)
        self.assertIn("mysql", step_ids)
        self.assertIn("ssc", step_ids)
        self.assertNotIn("lim", step_ids)
        self.assertNotIn("dast_core", step_ids)

    def test_dast_full_expands_dependencies(self) -> None:
        step_ids = expand_components(profile_components_for("dast_full"))

        for expected in ("postgresql", "ssc", "lim", "dast_core", "dast_scanner"):
            with self.subTest(expected=expected):
                self.assertIn(expected, step_ids)

    def test_full_lab_preserves_bash_profile_components(self) -> None:
        self.assertEqual(
            profile_components_for("full_lab"),
            ("ssc", "lim", "sast_controller", "sast_sensor", "dast_core", "dast_scanner"),
        )

    def test_custom_profile_can_be_session_only(self) -> None:
        profile = build_profile("custom", ("sast_sensor",))
        step_ids = [step.step_id for step in profile.steps]

        self.assertEqual(profile.label, "Custom")
        self.assertIn("sast_controller", step_ids)
        self.assertIn("sast_sensor", step_ids)


if __name__ == "__main__":
    unittest.main()
