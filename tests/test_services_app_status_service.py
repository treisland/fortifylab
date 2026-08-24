"""Unit tests for fortifylab.services.app_status_service (individual
component/pod status -- #446 slice, deployment & management parity)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.app_status_service import AppStatusService  # noqa: E402


def _pods_result(lines: list[str]) -> CommandResult:
    return CommandResult(args=(), returncode=0, stdout="\n".join(lines) + ("\n" if lines else ""), stderr="", duration_seconds=0.0)


class AppStatusServiceTests(unittest.TestCase):
    def test_not_deployed_when_no_pods_match_the_prefix(self) -> None:
        service = AppStatusService(runner=lambda args: _pods_result(["mysql-0   1/1   Running   0   1h"]))
        status = service.status("ssc-webapp")
        self.assertFalse(status.deployed)
        self.assertEqual((status.ready, status.total), (0, 0))

    def test_fully_ready_when_every_matching_pod_is_running_with_all_containers_ready(self) -> None:
        service = AppStatusService(
            runner=lambda args: _pods_result(
                [
                    "ssc-webapp-0   1/1   Running   0   1h",
                    "ssc-webapp-1   1/1   Running   0   1h",
                    "mysql-0        1/1   Running   0   1h",
                ]
            )
        )
        status = service.status("ssc-webapp")
        self.assertTrue(status.deployed)
        self.assertTrue(status.fully_ready)
        self.assertEqual((status.ready, status.total), (2, 2))

    def test_partially_ready_when_some_pods_are_not_fully_up(self) -> None:
        service = AppStatusService(
            runner=lambda args: _pods_result(
                [
                    "ssc-webapp-0   1/1   Running     0   1h",
                    "ssc-webapp-1   0/1   Pending     0   5s",
                ]
            )
        )
        status = service.status("ssc-webapp")
        self.assertTrue(status.deployed)
        self.assertFalse(status.fully_ready)
        self.assertEqual((status.ready, status.total), (1, 2))

    def test_running_but_not_all_containers_ready_does_not_count(self) -> None:
        # READY column "1/2" -- pod is Running but only 1 of 2 containers
        # ready; Bash's awk only counts a[1]==a[2].
        service = AppStatusService(runner=lambda args: _pods_result(["ssc-webapp-0   1/2   Running   0   1h"]))
        status = service.status("ssc-webapp")
        self.assertEqual((status.ready, status.total), (0, 1))

    def test_prefix_match_is_a_plain_startswith_not_a_glob(self) -> None:
        service = AppStatusService(
            runner=lambda args: _pods_result(["scancentral-sast-controller-0   1/1   Running   0   1h"])
        )
        status = service.status("scancentral-sast")
        self.assertEqual(status.total, 1)

    def test_kubectl_failure_reports_not_deployed_rather_than_raising(self) -> None:
        service = AppStatusService(runner=lambda args: CommandResult(args, 1, "", "connection refused", 0.0))
        status = service.status("ssc-webapp")
        self.assertEqual((status.ready, status.total), (0, 0))

    def test_statuses_bulk_fetches_every_app_from_a_single_kubectl_call(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            calls.append(args)
            return _pods_result(
                [
                    "ssc-webapp-0   1/1   Running   0   1h",
                    "mysql-0        1/1   Running   0   1h",
                ]
            )

        service = AppStatusService(runner=runner)
        results = service.statuses({"ssc": "ssc-webapp", "mysql": "mysql", "lim": "lim"})

        self.assertEqual(len(calls), 1)
        self.assertTrue(results["ssc"].fully_ready)
        self.assertTrue(results["mysql"].fully_ready)
        self.assertFalse(results["lim"].deployed)

    def test_statuses_bulk_reports_not_deployed_for_everything_on_kubectl_failure(self) -> None:
        service = AppStatusService(runner=lambda args: CommandResult(args, 1, "", "connection refused", 0.0))
        results = service.statuses({"ssc": "ssc-webapp", "mysql": "mysql"})
        self.assertEqual(set(results), {"ssc", "mysql"})
        self.assertFalse(results["ssc"].deployed)
        self.assertFalse(results["mysql"].deployed)

    def test_queries_the_services_own_namespace(self) -> None:
        seen: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            seen.append(args)
            return _pods_result([])

        AppStatusService(namespace="custom-ns", runner=runner).status("ssc-webapp")
        self.assertIn("custom-ns", seen[0])


if __name__ == "__main__":
    unittest.main()
