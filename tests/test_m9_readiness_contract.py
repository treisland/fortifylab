"""M9.6 setup/readiness TUI workflow contract tests.

These tests stay clone-safe: they use temporary ``.env`` fixtures and injected
doctor/status providers only, with no Kubernetes, Helm, Docker, network, or
credential access.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fortifylab.diagnostics import CheckStatus, DiagnosticResult, DiagnosticSection, DiagnosticSeverity, DoctorReport
from fortifylab.navigation import find_item
from fortifylab.status import ComponentStatus, LabStatus
from fortifylab.tui import workflows
from fortifylab.tui.readiness import (
    DEFAULT_RECOMMENDED_ACTIONS,
    ReadinessSignal,
    ReadinessSnapshot,
    ReadinessState,
    SetupReadinessScreen,
    build_setup_readiness_snapshot,
)


VALID_ENV = (
    "export NAMESPACE='fortify'\n"
    "export DOMAIN='demo.internal'\n"
    "export SSC='ssc.$DOMAIN'\n"
    "export LIM='lim.$DOMAIN'\n"
    "export SCDAST='dast.$DOMAIN'\n"
    "export SCSAST='sast.$DOMAIN'\n"
    "export SSC_URL='https://$SSC'\n"
    "export LIM_URL='https://$LIM'\n"
    "export LIM_API_URL='https://$LIM/LIM.API'\n"
    "export SCDAST_URL='https://$SCDAST'\n"
    "export SCSAST_URL='https://$SCSAST'\n"
    "export SCSAST_CTRL_URL='https://$SCSAST/scancentral-ctrl/'\n"
    "export DEFAULT_PASS='super-secret-password'\n"
    "export FORTIFY_LICENSE_FILE='/var/private/fortify.license'\n"
    "export FORTIFY_TLS_MODE='mkcert'\n"
)


class M9SetupReadinessContractTests(unittest.TestCase):
    def test_main_menu_setup_readiness_opens_real_workflow_screen(self) -> None:
        selected = find_item("main", "0")
        assert selected is not None

        result = workflows.dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertEqual(result.screen.id, "setup_readiness")
        self.assertEqual(result.screen.title, "Initial setup and readiness")
        self.assertIn("Overall readiness:", result.screen.render())
        self.assertNotIn("State machine boundary", result.screen.render())

    def test_default_snapshot_is_clone_safe_and_shows_unavailable_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = build_setup_readiness_snapshot(env_file=Path(directory) / ".env")

        by_id = {signal.id: signal for signal in snapshot.signals}
        self.assertEqual(by_id["config"].state, ReadinessState.WARN)
        self.assertEqual(by_id["license"].state, ReadinessState.SKIP)
        self.assertEqual(by_id["live_lab"].state, ReadinessState.SKIP)
        self.assertIn("Kubernetes/network checks deferred", by_id["live_lab"].summary)
        self.assertEqual(snapshot.actions, DEFAULT_RECOMMENDED_ACTIONS)
        self.assertEqual(snapshot.state, ReadinessState.WARN)

    def test_snapshot_uses_existing_config_validation_and_redacts_license_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(VALID_ENV.replace("demo.internal", "bad_domain", 1), encoding="utf-8")

            snapshot = build_setup_readiness_snapshot(env_file=env_path)
            screen = SetupReadinessScreen(snapshot_provider=lambda: snapshot)
            rendered = screen.render()

        by_id = {signal.id: signal for signal in snapshot.signals}
        self.assertEqual(by_id["config"].state, ReadinessState.FAIL)
        self.assertEqual(by_id["license"].state, ReadinessState.WARN)
        self.assertIn("validation finding", by_id["config"].summary)
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("super-secret-password", rendered)
        self.assertNotIn("/var/private/fortify.license", rendered)

    def test_injected_doctor_and_status_providers_drive_contract_states(self) -> None:
        report = DoctorReport(
            "fixture doctor",
            (
                DiagnosticSection(
                    "prerequisites",
                    (
                        DiagnosticResult(
                            "prerequisites.helm",
                            CheckStatus.WARN,
                            DiagnosticSeverity.WARN,
                            "Helm is missing",
                            "fixture only",
                        ),
                    ),
                ),
            ),
        )
        status = LabStatus(
            namespace="fortify",
            cluster="fixture-cluster",
            components=(ComponentStatus("ssc", 0, 1, "pending", "fixture unavailable"),),
            warnings=("not ready",),
        )

        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(VALID_ENV, encoding="utf-8")
            snapshot = build_setup_readiness_snapshot(
                env_file=env_path,
                doctor_report_provider=lambda: report,
                status_provider=lambda: status,
            )

        by_id = {signal.id: signal for signal in snapshot.signals}
        self.assertEqual(by_id["prerequisites"].state, ReadinessState.WARN)
        self.assertEqual(by_id["live_lab"].state, ReadinessState.WARN)
        self.assertIn("1 warning", by_id["live_lab"].detail)

    def test_screen_supports_refresh_back_selection_and_handoff_contract(self) -> None:
        snapshots = [
            ReadinessSnapshot(
                (ReadinessSignal("config", "Configuration", ReadinessState.WARN, "first"),),
                DEFAULT_RECOMMENDED_ACTIONS,
            ),
            ReadinessSnapshot(
                (ReadinessSignal("config", "Configuration", ReadinessState.PASS, "second"),),
                DEFAULT_RECOMMENDED_ACTIONS,
            ),
        ]

        def provider() -> ReadinessSnapshot:
            return snapshots.pop(0)

        screen = SetupReadinessScreen(snapshot_provider=provider)

        self.assertIn("first", screen.render())
        self.assertEqual(screen.handle_key("2").message, "Selected readiness action 2: Open Doctor.")
        self.assertEqual(screen.handle_key("enter").message, "Open workflow target: doctor.")
        self.assertIsNotNone(screen.last_handoff)
        assert screen.last_handoff is not None
        self.assertEqual(screen.last_handoff.workflow_target, "doctor")
        self.assertEqual(screen.handle_key("r").message, "Refreshed setup readiness.")
        self.assertIn("second", screen.render())
        self.assertEqual(screen.handle_key("down").message, "Selected next readiness action.")
        self.assertTrue(screen.handle_key("b").exit_screen)

    def test_recommended_actions_hand_off_to_existing_workflow_targets(self) -> None:
        targets = {action.workflow_target for action in DEFAULT_RECOMMENDED_ACTIONS}

        self.assertEqual(
            targets,
            {"configuration_editor", "doctor", "status", "help_center", "lifecycle", "logs"},
        )


if __name__ == "__main__":
    unittest.main()
