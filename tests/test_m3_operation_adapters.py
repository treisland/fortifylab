"""M3 contract tests for Python operation adapters.

These tests are intentionally noninteractive. They define the operation catalog
and runner contracts expected by the TUI migration without invoking Kubernetes,
Helm, Docker, network services, or real mutating commands.
"""

from __future__ import annotations

import importlib
import unittest
from typing import Any


operations = importlib.import_module("fortifylab.operations")


M3_DEPENDENCY = (
    "M3 operation adapter contract depends on fortifylab.operations exposing "
    "OperationCatalog, OperationRunner, CommandResult, and redact_text from "
    "agent/operations-M3-adapter-catalog."
)

REQUIRED_SYMBOLS = (
    "CommandResult",
    "OperationCatalog",
    "OperationImpact",
    "OperationRunner",
    "redact_text",
)
HAS_OPERATIONS_API = all(hasattr(operations, name) for name in REQUIRED_SYMBOLS)


def value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def enum_value(obj: Any) -> str:
    return str(value(obj, "value", obj))


@unittest.skipUnless(HAS_OPERATIONS_API, M3_DEPENDENCY)
class M3OperationAdapterTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.catalog = operations.OperationCatalog()

    def test_catalog_exposes_stable_operation_ids_and_command_plans(self) -> None:
        specs = tuple(self.catalog.list())
        ids = tuple(value(spec, "operation_id") for spec in specs)

        self.assertEqual(len(ids), len(set(ids)))
        for operation_id in (
            "certificates.create",
            "secrets.create",
            "app.ssc.start",
            "app.ssc.stop",
            "logs.ssc-webapp",
            "runbook.deployment",
        ):
            self.assertIn(operation_id, ids)

        secrets = self.catalog.get("secrets.create")
        plan = value(secrets, "plan", secrets)
        command = value(plan, "command")
        preview = value(plan, "preview")

        self.assertIsInstance(command, tuple)
        self.assertGreater(len(command), 0)
        self.assertIsInstance(preview, str)
        self.assertIn("create-secrets", " ".join(command))
        self.assertEqual(enum_value(value(secrets, "impact")), "mutation")

    def test_dry_run_returns_preview_without_executing_command(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_executor(command: tuple[str, ...]) -> Any:
            calls.append(command)
            return operations.CommandResult(command, 0, "executed", "", 0.01)

        runner = operations.OperationRunner(fake_executor)
        result = runner.run(self.catalog.get("secrets.create"))

        self.assertTrue(value(result, "ok"))
        self.assertFalse(value(result, "executed"))
        self.assertEqual(calls, [])
        self.assertIn("create-secrets", value(result, "preview"))
        self.assertIn("Dry run", value(result, "detail"))

    def test_mutating_operations_require_confirmation_before_execution(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_executor(command: tuple[str, ...]) -> Any:
            calls.append(command)
            return operations.CommandResult(command, 0, "changed", "", 0.01)

        runner = operations.OperationRunner(fake_executor)
        spec = self.catalog.get("app.ssc.stop")

        blocked = runner.run(spec, execute=True)

        self.assertFalse(value(blocked, "ok"))
        self.assertFalse(value(blocked, "executed"))
        self.assertEqual(calls, [])
        self.assertIn(value(spec, "confirmation"), value(blocked, "detail"))

        executed = runner.run(spec, execute=True, confirmation=value(spec, "confirmation"))

        self.assertTrue(value(executed, "ok"))
        self.assertTrue(value(executed, "executed"))
        self.assertEqual(len(calls), 1)

    def test_mocked_subprocess_success_and_failure_are_modeled(self) -> None:
        runner = operations.OperationRunner(
            lambda command: operations.CommandResult(command, 7, "partial output", "failed hard", 0.02)
        )

        result = runner.run(
            self.catalog.get("logs.ssc-webapp"),
            execute=True,
        )

        self.assertTrue(value(result, "executed"))
        self.assertFalse(value(result, "ok"))
        self.assertEqual(value(result, "returncode"), 7)
        self.assertIn("partial output", value(result, "stdout"))
        self.assertIn("failed hard", value(result, "stderr"))

    def test_command_result_tracks_stdout_stderr_returncode_and_duration(self) -> None:
        command_result = operations.CommandResult(
            ("fortifylab-safe-command", "--flag"),
            0,
            "stdout text",
            "stderr text",
            0.25,
        )

        self.assertTrue(value(command_result, "ok"))
        self.assertEqual(value(command_result, "command"), ("fortifylab-safe-command", "--flag"))
        self.assertEqual(value(command_result, "returncode"), 0)
        self.assertEqual(value(command_result, "stdout"), "stdout text")
        self.assertEqual(value(command_result, "stderr"), "stderr text")
        self.assertGreaterEqual(value(command_result, "duration_seconds"), 0.25)

    def test_secret_redaction_applies_to_commands_logs_and_results(self) -> None:
        secret_text = (
            "password=hunter2 token=abc123 api_key=key123 "
            "Authorization: Bearer very-secret"
        )
        redacted = operations.redact_text(secret_text)

        for leaked in ("hunter2", "abc123", "key123", "Bearer very-secret"):
            self.assertNotIn(leaked, redacted)
        self.assertIn("password=<redacted>", redacted)
        self.assertIn("token=<redacted>", redacted)
        self.assertIn("Authorization: <redacted>", redacted)

        runner = operations.OperationRunner(
            lambda command: operations.CommandResult(
                command,
                0,
                "created token=abc123",
                "password=hunter2",
                0.01,
            )
        )
        result = runner.run(
            self.catalog.get("secrets.create"),
            execute=True,
            confirmation=value(self.catalog.get("secrets.create"), "confirmation"),
        )

        rendered = " ".join(
            (
                " ".join(value(result, "command")),
                value(result, "stdout"),
                value(result, "stderr"),
                value(result, "detail"),
            )
        )
        for leaked in ("abc123", "hunter2"):
            self.assertNotIn(leaked, rendered)
        self.assertIn("<redacted>", rendered)


if __name__ == "__main__":
    unittest.main()
