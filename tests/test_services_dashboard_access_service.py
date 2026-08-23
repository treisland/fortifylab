"""Unit tests for fortifylab.services.dashboard_access_service (#446 slice 3)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.dashboard_access_service import DashboardAccessService  # noqa: E402


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(args=("kubectl",), returncode=0, stdout=stdout, stderr="", duration_seconds=0.0)


def _fail(stderr: str = "not found") -> CommandResult:
    return CommandResult(args=("kubectl",), returncode=1, stdout="", stderr=stderr, duration_seconds=0.0)


class DashboardAccessServiceNamespaceTests(unittest.TestCase):
    def test_namespace_is_kubernetes_dashboard_when_kong_proxy_service_exists(self) -> None:
        service = DashboardAccessService(runner=lambda args: _ok())
        self.assertEqual(service.namespace(), "kubernetes-dashboard")

    def test_namespace_falls_back_to_kube_system(self) -> None:
        service = DashboardAccessService(runner=lambda args: _fail())
        self.assertEqual(service.namespace(), "kube-system")


class DashboardAccessServiceResourcesReadyTests(unittest.TestCase):
    def test_ready_when_every_resource_exists(self) -> None:
        service = DashboardAccessService(runner=lambda args: _ok())
        self.assertTrue(service.resources_ready())

    def test_not_ready_when_any_resource_is_missing(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            calls.append(args)
            # Namespace probe ok, but the third resource check fails.
            if "serviceaccount/fortify-dashboard-admin" in args:
                return _fail()
            return _ok()

        service = DashboardAccessService(runner=runner)
        self.assertFalse(service.resources_ready())


class DashboardAccessServiceTokenTests(unittest.TestCase):
    def test_create_viewer_token_uses_the_viewer_service_account(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            calls.append(args)
            if "get" in args:
                return _ok()
            return _ok("fake-jwt-token")

        service = DashboardAccessService(runner=runner)
        result = service.create_viewer_token()

        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "fake-jwt-token")
        create_call = next(call for call in calls if "create" in call)
        self.assertIn("fortify-dashboard-viewer", create_call)
        self.assertNotIn("fortify-dashboard-admin", create_call)

    def test_create_admin_token_uses_the_admin_service_account(self) -> None:
        def runner(args: tuple[str, ...]) -> CommandResult:
            if "create" in args:
                return _ok("admin-jwt-token")
            return _ok()

        service = DashboardAccessService(runner=runner)
        result = service.create_admin_token()

        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "admin-jwt-token")

    def test_duration_defaults_to_one_hour(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            calls.append(args)
            return _ok("token")

        DashboardAccessService(runner=runner).create_viewer_token()
        create_call = next(call for call in calls if "create" in call)
        self.assertIn("1h", create_call)


if __name__ == "__main__":
    unittest.main()
