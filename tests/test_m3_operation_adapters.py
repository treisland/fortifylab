"""M3 operation adapter tests.

The tests exercise catalog contracts, previews, confirmation gates, and runner
redaction with harmless commands only. They must not run Kubernetes, Helm,
Docker, or repository lifecycle scripts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fortifylab.operations import (
    CommandPlan,
    Operation,
    OperationCategory,
    OperationConfirmationRequired,
    SensitiveRedactor,
    dry_run,
    get_operation,
    list_operations,
    preview_operation,
    run_operation,
)


ROOT = Path(__file__).resolve().parents[1]


class M3OperationCatalogTests(unittest.TestCase):
    def test_catalog_contains_stable_lifecycle_script_entries(self) -> None:
        ids = tuple(operation.id for operation in list_operations())

        for operation_id in (
            "mysql.start",
            "mysql.stop",
            "mysql.destroy",
            "ssc.start",
            "scancentral_dast.start",
            "juice_shop.destroy",
            "lab.start.all",
            "lab.stop.all",
            "lab.destroy.all",
        ):
            with self.subTest(operation_id=operation_id):
                self.assertIn(operation_id, ids)

        dast = get_operation("scancentral_dast.start")
        self.assertEqual(
            tuple(command.argv for command in dast.command_plan),
            (
                ("bash", "apps/scdast/core/start.sh"),
                ("bash", "apps/scdast/scanner/start.sh"),
            ),
        )

    def test_catalog_scripts_are_retained_low_level_app_adapters(self) -> None:
        for operation in list_operations():
            for command in operation.command_plan:
                with self.subTest(operation_id=operation.id, argv=command.argv):
                    self.assertEqual(command.argv[0], "bash")
                    script = command.argv[1]
                    self.assertTrue(
                        script.startswith("apps/"),
                        f"{operation.id} should use apps/** lifecycle adapters, got {script}",
                    )
                    self.assertRegex(script, r"/(?:start|stop|destroy)\.sh$")
                    self.assertTrue((ROOT / script).is_file(), script)

    def test_mutating_operations_require_confirmation_metadata(self) -> None:
        for operation in list_operations():
            with self.subTest(operation_id=operation.id):
                self.assertTrue(operation.mutating)
                self.assertTrue(operation.confirmation_required)
                self.assertIsInstance(operation.confirmation_prompt, str)
                self.assertGreater(len(operation.confirmation_prompt.strip()), 0)

    def test_lab_destroy_all_uses_reverse_dependency_order(self) -> None:
        preview = preview_operation("lab.destroy.all")

        self.assertEqual(preview.operation_id, "lab.destroy.all")
        self.assertEqual(
            preview.commands,
            (
                "bash apps/scdast/core/destroy.sh",
                "bash apps/scdast/scanner/destroy.sh",
                "bash apps/scsast/destroy.sh",
                "bash apps/lim/destroy.sh",
                "bash apps/ssc/destroy.sh",
                "bash apps/postgresql/destroy.sh",
                "bash apps/mysql/destroy.sh",
            ),
        )

    def test_dry_run_preview_does_not_execute_commands(self) -> None:
        operation = Operation(
            id="test.preview",
            label="Preview only",
            category=OperationCategory.SUPPORT,
            command_plan=(CommandPlan((sys.executable, "-c", "raise SystemExit(99)")),),
            mutating=True,
            confirmation_required=True,
            confirmation_prompt="Confirm preview only.",
        )

        preview = dry_run(operation)

        self.assertEqual(preview.commands[0], f"{sys.executable} -c raise SystemExit(99)")


class M3OperationRunnerTests(unittest.TestCase):
    def test_runner_refuses_unconfirmed_mutating_operation(self) -> None:
        with self.assertRaises(OperationConfirmationRequired):
            run_operation("mysql.start")

    def test_runner_executes_harmless_confirmed_operation(self) -> None:
        operation = Operation(
            id="test.harmless",
            label="Harmless",
            category=OperationCategory.SUPPORT,
            command_plan=(
                CommandPlan(
                    (
                        sys.executable,
                        "-c",
                        "import sys; print('ok token=abc123'); print('password=hunter2', file=sys.stderr)",
                    )
                ),
            ),
            mutating=True,
            confirmation_required=True,
            confirmation_prompt="Confirm harmless test.",
        )

        result = run_operation(operation, confirmed=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(result.commands), 1)
        self.assertGreaterEqual(result.commands[0].duration_seconds, 0)
        self.assertIn("token=<redacted>", result.commands[0].stdout)
        self.assertIn("password=<redacted>", result.commands[0].stderr)

    def test_runner_stops_after_first_failed_command(self) -> None:
        operation = Operation(
            id="test.failure",
            label="Failure",
            category=OperationCategory.SUPPORT,
            command_plan=(
                CommandPlan((sys.executable, "-c", "raise SystemExit(7)")),
                CommandPlan((sys.executable, "-c", "raise SystemExit(0)")),
            ),
            mutating=True,
            confirmation_required=True,
            confirmation_prompt="Confirm failing test.",
        )

        result = run_operation(operation, confirmed=True)

        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 7)
        self.assertEqual(len(result.commands), 1)

    def test_redactor_masks_sensitive_values_and_paths(self) -> None:
        redactor = SensitiveRedactor(extra_values=("explicit-secret",))
        text = (
            "token=abc123 password=hunter2 Bearer aaa.bbb "
            "/home/test/.ssh/github-treisland-agent "
            "/repo/secrets/input/fortify.license explicit-secret"
        )

        redacted = redactor.text(text)

        self.assertNotIn("abc123", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("aaa.bbb", redacted)
        self.assertNotIn("github-treisland-agent", redacted)
        self.assertNotIn("fortify.license", redacted)
        self.assertNotIn("explicit-secret", redacted)


if __name__ == "__main__":
    unittest.main()
