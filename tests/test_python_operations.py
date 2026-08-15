"""Contracts for Phase 3.6 Python operation commands."""

from __future__ import annotations

import threading
import time
import unittest

from fortifylab.core.command import CommandResult
from fortifylab.operations import OperationCatalog, OperationImpact, OperationJobManager, OperationJobRequest, OperationJobStatus, OperationKind, OperationRunner, log_selection_decision, matching_pods, should_skip_selection


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
        self.assertEqual(catalog.certs().command, ("bash", "./scripts/create-certs.sh"))
        self.assertEqual(catalog.secrets().command, ("bash", "./scripts/create-secrets.sh"))
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


    def test_log_selection_decision_reports_single_multiple_and_none(self) -> None:
        pods = ("ssc-webapp-0", "ssc-webapp-1", "mysql-0")

        self.assertEqual(log_selection_decision(pods, "mysql").decision, "single")
        self.assertEqual(log_selection_decision(pods, "ssc-webapp").decision, "multiple")
        self.assertEqual(log_selection_decision(pods, "lim").decision, "none")
        self.assertIn("decision=single", log_selection_decision(pods, "mysql").shell_lines())

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

        blocked = runner.run(OperationCatalog().secrets(), execute=True)
        result = runner.run(OperationCatalog().secrets(), execute=True, confirmation="REFRESH SECRETS")

        self.assertFalse(blocked.executed)
        self.assertIn("REFRESH SECRETS", blocked.detail)
        self.assertTrue(result.executed)
        self.assertTrue(result.ok)
        self.assertEqual(result.detail, "created")
        self.assertEqual(result.returncode, 0)
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.ended_at)
        self.assertIsNotNone(result.log_file)


    def test_job_manager_tracks_dry_run_mutation_without_calling_adapter(self) -> None:
        def fail_if_called(command: tuple[str, ...]) -> CommandResult:
            raise AssertionError(f"unexpected execution: {command}")

        manager = OperationJobManager(runner=OperationRunner(fail_if_called))
        job, created = manager.submit(OperationJobRequest("app.ssc.stop"))
        job = wait_for_job(manager, job.job_id)

        self.assertTrue(created)
        self.assertEqual(job.status, OperationJobStatus.COMPLETE)
        self.assertFalse(job.execution.executed if job.execution else True)
        self.assertIn("Dry run", job.message)
        self.assertEqual([entry.action for entry in job.audit], ["job.queued", "job.started", "job.finished"])

    def test_job_manager_prevents_duplicate_active_operation(self) -> None:
        release = threading.Event()

        def slow_runner(command: tuple[str, ...]) -> CommandResult:
            release.wait(timeout=2)
            return CommandResult(command, 0, "logs", "", 0.01)

        manager = OperationJobManager(runner=OperationRunner(slow_runner))
        first, first_created = manager.submit(OperationJobRequest("logs.ssc-webapp-0"))
        duplicate, duplicate_created = manager.submit(OperationJobRequest("logs.ssc-webapp-0"))
        release.set()
        final = wait_for_job(manager, first.job_id)

        self.assertTrue(first_created)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate.job_id, first.job_id)
        self.assertEqual(duplicate.duplicate_of, first.job_id)
        self.assertEqual(final.status, OperationJobStatus.COMPLETE)

    def test_job_payload_redacts_and_bounds_output_summary(self) -> None:
        secret_output = "password=supersecret " + ("x" * 1400)
        manager = OperationJobManager(runner=OperationRunner(lambda command: CommandResult(command, 0, secret_output, "", 0.01)))

        job, _ = manager.submit(OperationJobRequest("logs.ssc-webapp-0"))
        payload = wait_for_job(manager, job.job_id).to_api_dict()

        rendered = str(payload)
        self.assertNotIn("supersecret", rendered)
        self.assertIn("<redacted>", rendered)
        self.assertIn("omitted", payload["message"])
        self.assertLess(len(payload["execution"]["stdout_summary"]), 1300)

    def test_operation_runner_redacts_injected_runner_output(self) -> None:
        runner = OperationRunner(lambda command: CommandResult(command, 1, "", "token=abc123", 0.01))

        result = runner.run(OperationCatalog().logs("ssc-webapp-0", follow=False))

        self.assertFalse(result.ok)
        self.assertNotIn("abc123", result.detail)
        self.assertIn("<redacted>", result.detail)

    def test_timeout_result_shape_is_preserved(self) -> None:
        runner = OperationRunner(lambda command: CommandResult(command, 124, "", "timed out", 5.0, timed_out=True))

        result = runner.run(OperationCatalog().logs("ssc-webapp-0", follow=False))

        self.assertTrue(result.executed)
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)


def wait_for_job(manager: OperationJobManager, job_id: str, *, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get_job(job_id)
        if job and not job.active:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


if __name__ == "__main__":
    unittest.main()
