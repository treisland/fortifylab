"""M9.3 Diagnostics/Status TUI workflow model tests.

These tests exercise clone-safe, noninteractive screen-model behavior. They do
not import Textual, execute Kubernetes/Docker/Helm commands, use credentials, or
require a live lab.
"""

from __future__ import annotations

import importlib
import unittest

from fortifylab.diagnostics import (
    CheckStatus,
    DiagnosticResult,
    DiagnosticSection,
    DiagnosticSeverity,
    DoctorReport,
)
from fortifylab.navigation import find_item
from fortifylab.status import ComponentStatus, LabStatus
from fortifylab.tui import workflows
from fortifylab.tui.workflows import dispatch_menu_item


def require_model_factory(factory_names: tuple[str, ...], module_name: str, class_names: tuple[str, ...]):
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            module = None
        else:
            raise
    if module is not None:
        for factory_name in factory_names:
            factory = getattr(module, factory_name, None)
            if callable(factory):
                return factory
        for class_name in class_names:
            cls = getattr(module, class_name, None)
            if cls is not None:
                return cls
    for factory_name in factory_names:
        factory = getattr(workflows, factory_name, None)
        if callable(factory):
            return factory
    raise AssertionError(
        "Diagnostics/Status TUI must expose one of "
        f"{', '.join(factory_names)}() or {module_name}."
        f"{'/'.join(class_names)} as a pure workflow model"
    )


def call_first(target: object, names: tuple[str, ...], *args, **kwargs):
    for name in names:
        value = getattr(target, name, None)
        if callable(value):
            return value(*args, **kwargs)
    joined = ", ".join(names)
    raise AssertionError(f"{target!r} must expose one of: {joined}")


def call_factory(factory, attempts: tuple[dict[str, object], ...]):
    errors: list[TypeError] = []
    for kwargs in attempts:
        try:
            return factory(**kwargs)
        except TypeError as exc:
            errors.append(exc)
    raise errors[-1]


def text_of(value: object) -> str:
    if value is None:
        return ""
    render = getattr(value, "render", None)
    if callable(render):
        return str(render())
    if isinstance(value, (list, tuple)):
        return "\n".join(text_of(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {text_of(item)}" for key, item in value.items())
    if hasattr(value, "__dict__"):
        return "\n".join(f"{key}: {text_of(item)}" for key, item in vars(value).items())
    return str(value)


def fixture_doctor_report(*, detail_suffix: str = "initial") -> DoctorReport:
    return DoctorReport(
        "Fixture Doctor",
        (
            DiagnosticSection(
                "fixture checks",
                (
                    DiagnosticResult(
                        "prereq.python",
                        CheckStatus.PASS,
                        DiagnosticSeverity.INFO,
                        "Python runtime",
                        f"ok {detail_suffix}",
                    ),
                    DiagnosticResult(
                        "license.file",
                        CheckStatus.WARN,
                        DiagnosticSeverity.WARN,
                        "License file",
                        "DEFAULT_PASS=super-secret token=abc123 Authorization: Bearer aaa.bbb",
                    ),
                    DiagnosticResult(
                        "cluster.api",
                        CheckStatus.FAIL,
                        DiagnosticSeverity.ERROR,
                        "Cluster API",
                        "api_key=secret-key path=/home/test/.ssh/github-treisland-agent",
                    ),
                    DiagnosticResult(
                        "pods.live",
                        CheckStatus.SKIP,
                        DiagnosticSeverity.INFO,
                        "Live pod inspection",
                        "deferred: clone-safe test fixture",
                    ),
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
        self.assertIn(result.screen.id, {"diagnostics", "diagnostics_doctor", "doctor"})
        rendered = result.screen.render()
        self.assertIn("Diagnostics", result.screen.title)
        self.assertIn("Doctor", rendered)
        self.assertNotIn("placeholder", rendered.lower())
        self.assertNotIn("workflow boundary", rendered.lower())

    def test_doctor_and_status_menu_actions_dispatch_to_real_workflow_screens(self) -> None:
        cases = (
            ("more_tools", "8", {"diagnostics", "diagnostics_doctor", "doctor"}, "Doctor"),
            ("more_tools", "12", {"status", "lab_status", "cluster_snapshot"}, "Status"),
        )

        for menu_id, key, screen_ids, heading in cases:
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None
                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsNotNone(result.screen)
                assert result.screen is not None
                self.assertIn(result.screen.id, screen_ids)
                self.assertIn(heading, result.screen.render())
                self.assertNotIn("modeled; operation wiring starts", result.message)


class M9DiagnosticsStatusModelTests(unittest.TestCase):
    def make_diagnostics_model(self, doctor_provider=None, status_provider=None) -> object:
        factory = require_model_factory(
            ("build_diagnostics_workflow", "build_doctor_workflow"),
            "fortifylab.tui.diagnostics_status",
            ("DiagnosticsScreen", "DoctorWorkflowScreen"),
        )
        return call_factory(
            factory,
            (
                {
                    "doctor_report_provider": doctor_provider or fixture_doctor_report,
                    "status_provider": status_provider or fixture_lab_status,
                },
                {"report_factory": doctor_provider or fixture_doctor_report},
                {"doctor_provider": doctor_provider or fixture_doctor_report},
                {},
            ),
        )

    def make_status_model(self, status_provider=None) -> object:
        factory = require_model_factory(
            ("build_status_workflow",),
            "fortifylab.tui.diagnostics_status",
            ("StatusScreen", "StatusWorkflowScreen"),
        )
        return call_factory(
            factory,
            (
                {"status_provider": status_provider or fixture_lab_status},
                {"status_factory": status_provider or fixture_lab_status},
                {},
            ),
        )

    def test_doctor_rendering_covers_pass_warn_fail_skip_and_redacts_secrets(self) -> None:
        model = self.make_diagnostics_model()

        rendered = text_of(call_first(model, ("render_doctor", "doctor", "doctor_panel", "render")))

        for expected in ("PASS", "WARN", "FAIL", "SKIP"):
            self.assertIn(expected, rendered)
        for expected in ("Python runtime", "License file", "Cluster API", "Live pod inspection"):
            self.assertIn(expected, rendered)
        for sensitive in ("super-secret", "abc123", "aaa.bbb", "secret-key", "github-treisland-agent"):
            self.assertNotIn(sensitive, rendered)
        self.assertIn("<redacted>", rendered)

    def test_status_rendering_summarizes_components_and_redacts_tui_output(self) -> None:
        model = self.make_status_model()

        rendered = text_of(call_first(model, ("render_status", "status", "status_panel", "render")))

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
        reports = iter(
            (
                fixture_doctor_report(detail_suffix="before-refresh"),
                fixture_doctor_report(detail_suffix="after-refresh"),
            )
        )
        model = self.make_diagnostics_model(doctor_provider=lambda: next(reports))

        initial = text_of(call_first(model, ("render", "current_view", "screen")))
        self.assertIn("before-refresh", initial)

        refresh = call_first(model, ("handle_key", "on_key"), "r")
        refreshed = text_of(call_first(model, ("render", "current_view", "screen")))

        self.assertFalse(getattr(refresh, "exit_screen", False))
        self.assertIn("after-refresh", refreshed)
        self.assertNotIn("before-refresh", refreshed)
        self.assertNotIn("super-secret", refreshed)

        back = call_first(model, ("handle_key", "on_key"), "b")
        self.assertTrue(getattr(back, "exit_screen", False))
        self.assertRegex(getattr(back, "message", "").lower(), r"back|return")


if __name__ == "__main__":
    unittest.main()
