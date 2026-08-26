"""M9.3 Diagnostics/Status TUI workflow model tests.

These tests exercise clone-safe, noninteractive screen-model behavior. They do
not import Textual, execute Kubernetes/Docker/Helm commands, use credentials, or
require a live lab.
"""

from __future__ import annotations

import unittest

from fortifylab.diagnostics import CheckStatus, DiagnosticResult, DiagnosticSection, DiagnosticSeverity, DoctorReport
from fortifylab.navigation import ActionKind, ActionRef, MenuItem, find_item
from fortifylab.status import ComponentStatus, LabStatus
from fortifylab.tui import workflows
from fortifylab.tui.workflows import dispatch_menu_item


def text_of(value: object) -> str:
    render = getattr(value, "render", None)
    if callable(render):
        return str(render())
    return "" if value is None else str(value)


def fixture_doctor_report(*, detail_suffix: str = "initial") -> DoctorReport:
    return DoctorReport(
        "Fixture Doctor",
        (
            DiagnosticSection(
                "fixture checks",
                (
                    DiagnosticResult("prereq.python", CheckStatus.PASS, DiagnosticSeverity.INFO, "Python runtime", f"ok {detail_suffix}"),
                    DiagnosticResult("license.file", CheckStatus.WARN, DiagnosticSeverity.WARN, "License file", "DEFAULT_PASS=super-secret token=abc123 Authorization: Bearer aaa.bbb"),
                    DiagnosticResult("cluster.api", CheckStatus.FAIL, DiagnosticSeverity.ERROR, "Cluster API", "api_key=secret-key path=/home/test/.ssh/github-treisland-agent"),
                    DiagnosticResult("pods.live", CheckStatus.SKIP, DiagnosticSeverity.INFO, "Live pod inspection", "deferred: clone-safe test fixture"),
                ),
            ),
        ),
    )


def fixture_lab_status(*, warning: str = "registry token=abc123 unavailable") -> LabStatus:
    return LabStatus(
        namespace="fortify",
        cluster="fixture-cluster",
        components=(
            ComponentStatus("mysql", 1, 1, "ready"),
            ComponentStatus("ssc", 0, 1, "degraded", "password=hunter2 pod pending"),
            ComponentStatus("scancontroller", 1, 1, "ready"),
        ),
        warnings=(warning,),
    )


class M9DiagnosticsStatusDispatchTests(unittest.TestCase):
    def test_diagnostics_menu_opens_real_workflow_screen(self) -> None:
        selected = find_item("more_tools", "8")
        assert selected is not None

        result = dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertEqual(result.screen.id, "diagnostics")
        self.assertIn("Diagnostics", result.screen.title)
        self.assertIn("Doctor", result.screen.render())
        self.assertNotIn("placeholder", result.screen.render().lower())

    def test_doctor_and_status_actions_dispatch_to_real_workflow_screens(self) -> None:
        cases = (
            (MenuItem("d", "Doctor", ActionRef(ActionKind.COMMAND, "doctor", placeholder=False)), "doctor", "Doctor"),
            (MenuItem("s", "Status", ActionRef(ActionKind.COMMAND, "status", placeholder=False)), "status", "Status"),
        )

        for selected, screen_id, heading in cases:
            with self.subTest(screen_id=screen_id):
                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertEqual(result.screen.id, screen_id)
                self.assertIn(heading, result.screen.render())
                self.assertNotIn("modeled; operation wiring starts", result.message)


class M9DiagnosticsStatusModelTests(unittest.TestCase):
    def test_doctor_rendering_covers_pass_warn_fail_skip_and_redacts_secrets(self) -> None:
        model = workflows.build_diagnostics_workflow(doctor_report_provider=fixture_doctor_report, status_provider=fixture_lab_status)

        rendered = model.render_doctor()

        for expected in ("PASS", "WARN", "FAIL", "SKIP"):
            self.assertIn(expected, rendered)
        for expected in ("Python runtime", "License file", "Cluster API", "Live pod inspection"):
            self.assertIn(expected, rendered)
        for sensitive in ("super-secret", "abc123", "aaa.bbb", "secret-key", "github-treisland-agent"):
            self.assertNotIn(sensitive, rendered)
        self.assertIn("<redacted>", rendered)

    def test_status_rendering_summarizes_components_and_redacts_tui_output(self) -> None:
        model = workflows.build_status_workflow(status_provider=fixture_lab_status)

        rendered = model.render_status()

        self.assertIn("fixture-cluster", rendered)
        self.assertIn("fortify", rendered)
        self.assertIn("2/3 components ready", rendered)
        self.assertIn("mysql", rendered)
        self.assertIn("ssc", rendered)
        self.assertIn("scancontroller", rendered)
        for sensitive in ("hunter2", "abc123"):
            self.assertNotIn(sensitive, rendered)
        self.assertIn("<redacted>", rendered)

    def test_refresh_updates_pure_model_and_back_exits_workflow(self) -> None:
        reports = iter((fixture_doctor_report(detail_suffix="before-refresh"), fixture_doctor_report(detail_suffix="after-refresh")))
        statuses = iter((fixture_lab_status(warning="before token=old-secret"), fixture_lab_status(warning="after token=new-secret")))
        model = workflows.build_diagnostics_workflow(doctor_report_provider=lambda: next(reports), status_provider=lambda: next(statuses))

        initial = text_of(model)
        self.assertIn("before-refresh", initial)
        self.assertNotIn("old-secret", initial)

        refresh = model.handle_key("r")
        refreshed = text_of(model)

        self.assertFalse(refresh.exit_screen)
        self.assertIn("after-refresh", refreshed)
        self.assertNotIn("before-refresh", refreshed)
        self.assertNotIn("new-secret", refreshed)

        back = model.handle_key("b")
        self.assertTrue(back.exit_screen)
        self.assertIn("back", back.message.lower())


if __name__ == "__main__":
    unittest.main()
