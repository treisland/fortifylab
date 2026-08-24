"""Contracts for Phase 3.6 Python operation commands."""

from __future__ import annotations

from pathlib import Path
import unittest

from fortifylab.core.command import CommandResult
from fortifylab.operations import OperationCatalog, OperationImpact, OperationKind, OperationRunner, matching_pods, should_skip_selection

REPO_ROOT = Path(__file__).resolve().parents[1]


class PythonOperationsTests(unittest.TestCase):
    def test_default_runner_calls_run_command_with_a_valid_timeout_kwarg(self) -> None:
        # Regression: _default_runner previously called run_command(...,
        # timeout_seconds=600), but run_command's real parameter is
        # `timeout` -- a TypeError on every real (non-injected-runner) use,
        # uncaught because every other test here injects a fake runner.
        result = OperationRunner._default_runner(("true",))
        self.assertTrue(result.ok)

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

    def test_catalog_supports_sample_apps_alongside_core_apps(self) -> None:
        # Sample apps (Juice Shop, WebGoat, DVWA) live under apps/samples/
        # rather than apps/<id>/ -- a distinct script path template from
        # the core apps, easy to get wrong when adding a new app id.
        catalog = OperationCatalog()
        self.assertEqual(catalog.app("juice-shop", "start").command, ("bash", "./apps/samples/juice-shop/start.sh"))
        self.assertEqual(catalog.app("webgoat", "stop").command, ("bash", "./apps/samples/webgoat/stop.sh"))
        self.assertEqual(catalog.app("dvwa", "start").command, ("bash", "./apps/samples/dvwa/start.sh"))

    def test_unsupported_app_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            OperationCatalog().app("not-a-real-app", "start")

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

    def test_logs_command_uses_the_given_namespace_not_a_hardcoded_default(self) -> None:
        # Regression test: catalog.logs() used to hardcode "-n fortify"
        # regardless of the caller's actual namespace, so a lab whose pods
        # were correctly listed in a custom namespace would still try to
        # tail their logs from the wrong one.
        spec = OperationCatalog().logs("ssc-webapp-0", follow=False, namespace="custom-ns")
        self.assertIn("custom-ns", spec.command)
        self.assertNotIn("fortify", spec.command)

    def test_non_mutating_logs_can_execute_without_execute_flag(self) -> None:
        calls: list[tuple[str, ...]] = []
        runner = OperationRunner(lambda command: calls.append(command) or CommandResult(command, 0, "logs", "", 0.01))

        result = runner.run(OperationCatalog().logs("ssc-webapp-0", follow=True))

        self.assertTrue(result.executed)
        self.assertTrue(result.ok)
        self.assertEqual(calls[0], ("microk8s", "kubectl", "-n", "fortify", "logs", "ssc-webapp-0", "-f"))

    def test_every_real_script_operation_is_invoked_via_bash_and_exists(self) -> None:
        # Regression test: catalog.app()/certs()/secrets() used to execute
        # their script paths directly, relying on the executable bit.
        # Those scripts are intentionally NOT executable in git (the Bash
        # wizard's own convention is to always invoke them via `bash
        # "$path"`) -- executing one directly hits PermissionError on a
        # real clone, exactly the bug already fixed once for
        # orchestration.adapters.DEFAULT_STEP_SCRIPTS but missed here.
        catalog = OperationCatalog()
        specs = [
            catalog.certs(),
            catalog.secrets(),
            *(catalog.app(app_id, action) for app_id in ("ssc", "lim", "mysql", "postgresql") for action in ("start", "stop")),
            *(catalog.app(app_id, "start") for app_id in ("juice-shop", "webgoat", "dvwa")),
        ]
        for spec in specs:
            self.assertEqual(spec.command[0], "bash", f"{spec.operation_id} must be invoked via bash")
            script_path = spec.command[1].removeprefix("./")
            self.assertTrue((REPO_ROOT / script_path).is_file(), f"{spec.operation_id}: {script_path} does not exist")

    def test_execute_flag_runs_mutating_operation_through_injected_runner(self) -> None:
        runner = OperationRunner(lambda command: CommandResult(command, 0, "created", "", 0.01))

        result = runner.run(OperationCatalog().secrets(), execute=True)

        self.assertTrue(result.executed)
        self.assertTrue(result.ok)
        self.assertEqual(result.detail, "created")


if __name__ == "__main__":
    unittest.main()
