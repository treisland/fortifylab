"""Contracts for Phase 3.6 Python operation commands."""

from __future__ import annotations

import unittest

from fortifylab.core.command import CommandResult
from fortifylab.operations import OperationCatalog, OperationImpact, OperationKind, OperationRunner, matching_pods, should_skip_selection


class PythonOperationsTests(unittest.TestCase):
    def test_catalog_describes_certificate_secret_app_log_and_runbook_operations(self) -> None:
        catalog = OperationCatalog()
        specs = catalog.list()
        kinds = {spec.kind for spec in specs}

        self.assertIn(OperationKind.CERTIFICATE, kinds)
        self.assertIn(OperationKind.SECRET, kinds)
        self.assertIn(OperationKind.APP_LIFECYCLE, kinds)
        self.assertIn(OperationKind.LOGS, kinds)
        self.assertIn(OperationKind.RUNBOOK, kinds)
        self.assertEqual(catalog.certs().command, ("./scripts/create-certs.sh",))
        self.assertEqual(catalog.secrets().command, ("./scripts/create-secrets.sh",))
        self.assertEqual(catalog.secrets().impact, OperationImpact.MUTATION)
        self.assertIn("secret.key", catalog.secrets().warning)

    def test_mutating_operations_are_dry_run_by_default(self) -> None:
        calls: list[tuple[str, ...]] = []
        runner = OperationRunner(lambda command: calls.append(command) or CommandResult(command, 0, "ok", "", 0.01))

        result = runner.run(OperationCatalog().app("ssc", "stop"))

        self.assertFalse(result.executed)
        self.assertTrue(result.ok)
        self.assertEqual(calls, [])
        self.assertIn("Dry run", result.detail)

    def test_destructive_operation_requires_typed_confirmation(self) -> None:
        runner = OperationRunner(lambda command: CommandResult(command, 0, "destroyed", "", 0.01))
        spec = OperationCatalog().app("ssc", "destroy")

        blocked = runner.run(spec, execute=True)
        executed = runner.run(spec, execute=True, confirmation="DESTROY ssc")

        self.assertFalse(blocked.executed)
        self.assertFalse(blocked.ok)
        self.assertIn("DESTROY ssc", blocked.detail)
        self.assertTrue(executed.executed)
        self.assertTrue(executed.ok)

    def test_lifecycle_plan_reverses_shutdown_order(self) -> None:
        catalog = OperationCatalog()

        start = catalog.lifecycle_plan("start", ("mysql", "postgresql", "ssc"))
        shutdown = catalog.lifecycle_plan("shutdown", ("mysql", "postgresql", "ssc"))

        self.assertEqual([spec.operation_id for spec in start], ["app.mysql.start", "app.postgresql.start", "app.ssc.start"])
        self.assertEqual([spec.operation_id for spec in shutdown], ["app.ssc.stop", "app.postgresql.stop", "app.mysql.stop"])

    def test_log_selection_skips_redundant_selection_for_single_match(self) -> None:
        pods = ("ssc-webapp-0", "mysql-0")

        self.assertEqual(matching_pods(pods, "ssc-webapp"), ("ssc-webapp-0",))
        self.assertTrue(should_skip_selection(pods, "ssc-webapp"))
        self.assertFalse(should_skip_selection(("ssc-webapp-0", "ssc-webapp-1"), "ssc-webapp"))

    def test_runbook_renderer_blocks_unknown_topics(self) -> None:
        with self.assertRaises(ValueError):
            OperationCatalog().runbook("../../.env")

    def test_non_mutating_logs_can_execute_without_execute_flag(self) -> None:
        calls: list[tuple[str, ...]] = []
        runner = OperationRunner(lambda command: calls.append(command) or CommandResult(command, 0, "logs", "", 0.01))

        result = runner.run(OperationCatalog().logs("ssc-webapp-0", follow=True))

        self.assertTrue(result.executed)
        self.assertTrue(result.ok)
        self.assertEqual(calls[0], ("microk8s", "kubectl", "-n", "fortify", "logs", "ssc-webapp-0", "-f"))

    def test_execute_flag_runs_mutating_operation_through_injected_runner(self) -> None:
        runner = OperationRunner(lambda command: CommandResult(command, 0, "created", "", 0.01))

        result = runner.run(OperationCatalog().secrets(), execute=True)

        self.assertTrue(result.executed)
        self.assertTrue(result.ok)
        self.assertEqual(result.detail, "created")


if __name__ == "__main__":
    unittest.main()
