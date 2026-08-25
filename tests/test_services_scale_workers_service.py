"""Unit tests for fortifylab.services.scale_workers_service.ScaleWorkersService
-- the replacement for scale_workers() in scripts/wizard/operations.sh."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.scale_workers_service import ScaleWorkersService  # noqa: E402


class ScaleWorkersServiceTests(unittest.TestCase):
    def test_statefulset_for_sast_and_dast(self) -> None:
        service = ScaleWorkersService()
        self.assertEqual(service.statefulset_for("sast"), "scancentral-sast-worker-linux")
        self.assertEqual(service.statefulset_for("dast"), "sdast-scanner-scancentral-dast-scanner")

    def test_statefulset_for_unsupported_app_is_none(self) -> None:
        service = ScaleWorkersService()
        for app_id in ("ssc", "lim", "mysql", "postgresql", "juice-shop"):
            self.assertIsNone(service.statefulset_for(app_id))

    def test_current_replicas_reads_the_statefulsets_spec(self) -> None:
        calls = []

        def runner(args):
            calls.append(args)
            return CommandResult(args, 0, "3", "", 0.0)

        service = ScaleWorkersService(runner=runner)
        self.assertEqual(service.current_replicas("sast"), "3")
        self.assertEqual(
            calls[0],
            ("-n", "fortify", "get", "statefulset", "scancentral-sast-worker-linux", "-o", "jsonpath={.spec.replicas}"),
        )

    def test_current_replicas_uses_the_configured_namespace(self) -> None:
        seen = []
        service = ScaleWorkersService(
            namespace="custom-ns", runner=lambda args: seen.append(args) or CommandResult(args, 0, "2", "", 0.0)
        )
        service.current_replicas("dast")
        self.assertIn("custom-ns", seen[0])

    def test_current_replicas_falls_back_to_unknown_marker_on_failure(self) -> None:
        service = ScaleWorkersService(runner=lambda args: CommandResult(args, 1, "", "not found", 0.0))
        self.assertEqual(service.current_replicas("sast"), "?")

    def test_current_replicas_falls_back_to_unknown_marker_on_blank_output(self) -> None:
        service = ScaleWorkersService(runner=lambda args: CommandResult(args, 0, "   ", "", 0.0))
        self.assertEqual(service.current_replicas("sast"), "?")

    def test_current_replicas_for_unsupported_app_is_unknown_without_a_kubectl_call(self) -> None:
        calls = []
        service = ScaleWorkersService(runner=lambda args: calls.append(args) or CommandResult(args, 0, "1", "", 0.0))
        self.assertEqual(service.current_replicas("ssc"), "?")
        self.assertEqual(calls, [])

    def test_scale_runs_kubectl_scale_with_the_given_replica_count(self) -> None:
        calls = []

        def runner(args):
            calls.append(args)
            return CommandResult(args, 0, "scaled", "", 0.0)

        service = ScaleWorkersService(runner=runner)
        result = service.scale("dast", "4")
        self.assertTrue(result.ok)
        self.assertEqual(
            calls[0],
            ("-n", "fortify", "scale", "statefulset", "sdast-scanner-scancentral-dast-scanner", "--replicas=4"),
        )

    def test_scale_for_unsupported_app_raises(self) -> None:
        service = ScaleWorkersService()
        with self.assertRaises(ValueError):
            service.scale("ssc", "3")


if __name__ == "__main__":
    unittest.main()
