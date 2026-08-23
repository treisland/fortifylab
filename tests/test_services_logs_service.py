"""Unit tests for fortifylab.services.logs_service (M4 of the TUI migration)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.operations import OperationRunner  # noqa: E402
from fortifylab.services.logs_service import LogsService  # noqa: E402


def _fake_result(stdout: str, ok: bool = True) -> CommandResult:
    return CommandResult(args=("kubectl",), returncode=0 if ok else 1, stdout=stdout, stderr="", duration_seconds=0.0)


class LogsServiceTests(unittest.TestCase):
    def test_matching_pods_filters_by_prefix(self) -> None:
        service = LogsService(pod_lister=lambda: ("ssc-webapp-0", "mysql-0", "ssc-webapp-1"))
        self.assertEqual(service.matching_pods("ssc-webapp"), ("ssc-webapp-0", "ssc-webapp-1"))

    def test_should_skip_selection_true_for_a_single_match(self) -> None:
        service = LogsService(pod_lister=lambda: ("mysql-0",))
        self.assertTrue(service.should_skip_selection("mysql"))

    def test_should_skip_selection_false_for_multiple_matches(self) -> None:
        service = LogsService(pod_lister=lambda: ("mysql-0", "mysql-1"))
        self.assertFalse(service.should_skip_selection("mysql"))

    def test_tail_runs_the_read_only_logs_operation_without_needing_execute(self) -> None:
        def fake_runner(command: tuple[str, ...]) -> CommandResult:
            self.assertIn("logs", command)
            return _fake_result("log line 1\nlog line 2\n")

        service = LogsService(runner=OperationRunner(fake_runner))
        execution = service.tail("ssc-webapp-0")
        self.assertTrue(execution.executed)
        self.assertTrue(execution.ok)
        self.assertIn("log line 1", execution.detail)


if __name__ == "__main__":
    unittest.main()
