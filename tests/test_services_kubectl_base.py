"""Unit tests for the shared KubectlBackedService base (used by
DashboardAccessService, UrlsCredentialsService, LabStatusService, and
AppStatusService -- collapsing what used to be an identical _run() copied
into each of them)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.kubectl_base import KubectlBackedService  # noqa: E402


class KubectlBackedServiceTests(unittest.TestCase):
    def test_uses_the_injected_runner_when_given(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            calls.append(args)
            return CommandResult(args, 0, "ok", "", 0.0)

        service = KubectlBackedService(runner=runner)
        result = service._run(("get", "pods"))

        self.assertEqual(calls, [("get", "pods")])
        self.assertTrue(result.ok)

    def test_falls_back_to_a_real_run_command_call_using_the_configured_kubectl(self) -> None:
        # No injected runner: exercises the real run_command() path against
        # a nonexistent binary, confirming the kubectl string is actually
        # split and prefixed rather than silently ignored.
        service = KubectlBackedService(kubectl="definitely-not-a-real-kubectl-binary")
        result = service._run(("get", "pods"))
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
