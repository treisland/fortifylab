"""M5 diagnostics and status contract tests.

These tests define read-only diagnostics behavior for the Python CLI/TUI
migration. They must not call Kubernetes, Helm, Docker, the network, or mutate
real Fortify Lab state. Implementation-dependent tests skip until the M5 public
APIs or CLI commands land.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def require_attrs(module_name: str, *names: str):
    module = importlib.import_module(module_name)
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        raise unittest.SkipTest(f"{module_name} missing M5 contract symbols: {', '.join(missing)}")
    return tuple(getattr(module, name) for name in names)


def enum_value(enum_cls, name: str):
    try:
        return enum_cls[name]
    except (KeyError, TypeError):
        return getattr(enum_cls, name)


class M5DiagnosticModelTests(unittest.TestCase):
    def test_diagnostic_check_and_result_models_capture_read_only_contract(self) -> None:
        DiagnosticCheck, DiagnosticResult, CheckStatus, DiagnosticSeverity = require_attrs(
            "fortifylab.diagnostics",
            "DiagnosticCheck",
            "DiagnosticResult",
            "CheckStatus",
            "DiagnosticSeverity",
        )

        check = DiagnosticCheck(
            id="cluster.kubectl.client",
            label="kubectl client is available",
            category="prerequisites",
            severity=enum_value(DiagnosticSeverity, "ERROR"),
            command=("kubectl", "version", "--client"),
            requires_network=False,
            mutating=False,
        )
        result = DiagnosticResult(
            check_id=check.id,
            status=enum_value(CheckStatus, "PASS"),
            severity=check.severity,
            summary="kubectl client is available",
            detail="client version found",
            duration_seconds=0.01,
        )

        self.assertEqual(check.id, "cluster.kubectl.client")
        self.assertEqual(tuple(check.command), ("kubectl", "version", "--client"))
        self.assertFalse(check.requires_network)
        self.assertFalse(check.mutating)
        self.assertEqual(result.check_id, check.id)
        self.assertTrue(result.ok)

    def test_default_check_catalog_declares_expected_read_only_categories(self) -> None:
        (default_checks,) = require_attrs("fortifylab.diagnostics", "default_checks")

        checks = tuple(default_checks())
        categories = {check.category for check in checks}

        for category in ("prerequisites", "license", "cluster", "pods", "registry", "tls"):
            with self.subTest(category=category):
                self.assertIn(category, categories)

        for check in checks:
            with self.subTest(check_id=check.id):
                self.assertFalse(check.mutating)
                if getattr(check, "command", ()):
                    forbidden = {"apply", "create", "delete", "destroy", "install", "patch", "restart"}
                    self.assertFalse(forbidden.intersection(set(check.command)))

    def test_runner_uses_injected_executor_and_never_shells_out_in_contract_tests(self) -> None:
        (
            DiagnosticCheck,
            DiagnosticCommandResult,
            DiagnosticRunner,
            CheckStatus,
            DiagnosticSeverity,
        ) = require_attrs(
            "fortifylab.diagnostics",
            "DiagnosticCheck",
            "DiagnosticCommandResult",
            "DiagnosticRunner",
            "CheckStatus",
            "DiagnosticSeverity",
        )

        commands: list[tuple[str, ...]] = []

        def fake_executor(command: tuple[str, ...]) -> DiagnosticCommandResult:
            commands.append(command)
            return DiagnosticCommandResult(command=command, exit_code=0, stdout="ok", stderr="", duration_seconds=0.01)

        checks = (
            DiagnosticCheck(
                id="registry.auth",
                label="registry auth can be inspected",
                category="registry",
                severity=enum_value(DiagnosticSeverity, "WARN"),
                command=("kubectl", "get", "secret", "regcred", "-o", "json"),
                requires_network=False,
                mutating=False,
            ),
        )

        results = tuple(DiagnosticRunner(checks=checks, executor=fake_executor).run_all())

        self.assertEqual(commands, [("kubectl", "get", "secret", "regcred", "-o", "json")])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, enum_value(CheckStatus, "PASS"))

    def test_diagnostic_redactor_masks_secret_values_paths_and_command_output(self) -> None:
        (redact_diagnostic_text,) = require_attrs("fortifylab.diagnostics", "redact_diagnostic_text")
        text = (
            "DEFAULT_PASS=super-secret token=abc123 Authorization: Bearer aaa.bbb "
            "/home/test/.ssh/github-treisland-agent /repo/secrets/input/fortify.license "
            "stdout=password=hunter2 stderr=api_key=secret-key"
        )

        redacted = redact_diagnostic_text(text, extra_values=("super-secret", "secret-key"))

        for sensitive in (
            "super-secret",
            "abc123",
            "aaa.bbb",
            "github-treisland-agent",
            "fortify.license",
            "hunter2",
            "secret-key",
        ):
            with self.subTest(sensitive=sensitive):
                self.assertNotIn(sensitive, redacted)
        self.assertIn("<redacted>", redacted)


class M5StatusModelTests(unittest.TestCase):
    def test_lab_status_model_aggregates_components_without_live_checks(self) -> None:
        ComponentStatus, LabStatus = require_attrs("fortifylab.status", "ComponentStatus", "LabStatus")

        status = LabStatus(
            namespace="fortify",
            cluster="microk8s",
            components=(
                ComponentStatus(name="mysql", ready=1, desired=1, status="ready"),
                ComponentStatus(name="ssc", ready=0, desired=1, status="degraded", message="pod pending"),
            ),
            warnings=("ssc is not ready",),
        )

        self.assertEqual(status.namespace, "fortify")
        self.assertFalse(status.ok)
        self.assertEqual(status.summary, "1/2 components ready")
        self.assertEqual([component.name for component in status.components], ["mysql", "ssc"])


class M5DiagnosticsCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["NO_COLOR"] = "1"
        env["FORTIFYLAB_DIAGNOSTICS_TEST_MODE"] = "1"
        env["FORTIFYLAB_TEST_SECRET"] = "do-not-print"
        return subprocess.run(
            [str(ROOT / "bin" / "fortifylab"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def require_cli_command(self, command: str) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        if command not in result.stdout:
            raise unittest.SkipTest(f"fortifylab {command} command not implemented yet")

    def test_doctor_check_outputs_redacted_summary_and_success_exit_code(self) -> None:
        self.require_cli_command("doctor")

        result = self.run_cli("doctor", "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FortifyLab Doctor", result.stdout)
        self.assertIn("prerequisites", result.stdout)
        self.assertIn("cluster", result.stdout)
        self.assertIn("tls", result.stdout)
        self.assertNotIn("do-not-print", result.stdout + result.stderr)

    def test_doctor_strict_returns_nonzero_for_warning_or_failure_fixture(self) -> None:
        self.require_cli_command("doctor")

        result = self.run_cli("doctor", "--check", "--strict", "--scenario", "warning")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FortifyLab Doctor", result.stdout)
        self.assertIn("WARN", result.stdout)
        self.assertNotIn("do-not-print", result.stdout + result.stderr)

    def test_status_check_outputs_component_summary_without_live_dependencies(self) -> None:
        self.require_cli_command("status")

        result = self.run_cli("status", "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FortifyLab Status", result.stdout)
        self.assertIn("components", result.stdout)
        self.assertIn("cluster", result.stdout)
        self.assertNotIn("do-not-print", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
