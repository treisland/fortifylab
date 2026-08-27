"""M9.6 setup/readiness TUI workflow behavior tests.

These tests stay clone-safe: they use temporary ``.env`` fixtures and injected
providers only, with no Kubernetes, Helm, Docker, network, or credential access.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fortifylab.diagnostics import CheckStatus, DiagnosticResult, DiagnosticSection, DoctorReport
from fortifylab.navigation import find_item
from fortifylab.status import ComponentStatus, LabStatus
from fortifylab.tui.readiness import ReadinessState, SetupReadinessScreen, build_setup_readiness_snapshot
from fortifylab.tui.workflows import dispatch_menu_item


def doctor_report(*statuses: CheckStatus) -> DoctorReport:
    results = tuple(
        DiagnosticResult(f"check-{index}", status, "INFO", f"{status.value} summary")
        for index, status in enumerate(statuses, start=1)
    )
    return DoctorReport("fixture", (DiagnosticSection("prerequisites", results),))


class M9ReadinessWorkflowTests(unittest.TestCase):
    def test_setup_readiness_menu_options_open_real_workflow_screens(self) -> None:
        cases = (
            ("main", "0", "setup_readiness", "Initial setup and readiness"),
            ("more_tools", "0", "setup_readiness", "Initial setup and readiness"),
            ("setup_readiness", "1", "setup_readiness", "Initial setup and readiness"),
            ("setup_readiness", "2", "setup_readiness.reset_tiers", "Complete lab reset tiers"),
        )

        for menu_id, key, screen_id, title in cases:
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None

                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertEqual(result.screen.id, screen_id)
                self.assertEqual(result.screen.title, title)

    def test_snapshot_reports_missing_env_and_clone_safe_live_lab_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot = build_setup_readiness_snapshot(
                env_file=Path(tempdir) / ".env",
                doctor_report_provider=lambda: doctor_report(CheckStatus.PASS),
                status_provider=lambda: LabStatus("fortify", "clone-safe"),
            )

        states = {signal.id: signal.state for signal in snapshot.signals}
        self.assertEqual(states["config"], ReadinessState.WARN)
        self.assertEqual(states["license"], ReadinessState.SKIP)
        self.assertEqual(states["prerequisites"], ReadinessState.PASS)
        self.assertEqual(states["live_lab"], ReadinessState.SKIP)
        self.assertEqual(snapshot.state, ReadinessState.WARN)

    def test_snapshot_redacts_license_path_and_aggregates_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            env_file = Path(tempdir) / ".env"
            env_file.write_text("FORTIFY_LICENSE_FILE=/secret/path/license.lic\n", encoding="utf-8")

            snapshot = build_setup_readiness_snapshot(
                env_file=env_file,
                doctor_report_provider=lambda: doctor_report(CheckStatus.FAIL, CheckStatus.WARN),
                status_provider=lambda: LabStatus(
                    "fortify",
                    "fixture",
                    (ComponentStatus("ssc", 0, 1, "pending"),),
                    ("cluster token abc123",),
                ),
            )

        rendered = SetupReadinessScreen(snapshot_provider=lambda: snapshot).render()
        self.assertEqual(snapshot.state, ReadinessState.FAIL)
        self.assertIn("FAIL Prerequisites", rendered)
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("/secret/path/license.lic", rendered)
        self.assertNotIn("abc123", rendered)

    def test_readiness_actions_support_number_jump_refresh_back_and_handoff_targets(self) -> None:
        calls = {"count": 0}

        def snapshot_provider():
            calls["count"] += 1
            return build_setup_readiness_snapshot(
                env_file=Path("/tmp/fortifylab-missing-test-env"),
                doctor_report_provider=lambda: doctor_report(CheckStatus.PASS),
                status_provider=lambda: LabStatus("fortify", "clone-safe"),
            )

        screen = SetupReadinessScreen(snapshot_provider=snapshot_provider)

        self.assertIn("Recommended actions:", screen.render())
        select_result = screen.handle_key("3")
        self.assertIn("Open Status", select_result.message)
        handoff = screen.handle_key("enter")
        self.assertEqual(handoff.open_target, "status")
        self.assertFalse(handoff.exit_screen)
        refresh = screen.handle_key("r")
        self.assertEqual(refresh.message, "Refreshed setup readiness.")
        self.assertEqual(calls["count"], 2)
        self.assertTrue(screen.handle_key("b").exit_screen)

    def test_reset_tiers_screen_hands_off_without_mutation(self) -> None:
        selected = find_item("setup_readiness", "2")
        assert selected is not None
        result = dispatch_menu_item(selected)
        assert result.screen is not None

        rendered = result.screen.render()
        self.assertIn("Read-only reset guidance", rendered)
        self.assertIn("SKIP Lab reset", rendered)
        handoff = result.screen.handle_key("enter")
        self.assertEqual(handoff.open_target, "lifecycle")


if __name__ == "__main__":
    unittest.main()
