"""Safety and deployment contracts for the default Kubernetes Dashboard."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from tests.wizard_source import read_wizard_source


ROOT = Path(__file__).resolve().parents[1]


class DashboardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wizard = read_wizard_source(ROOT)
        cls.deploy = (
            ROOT / "apps/kubernetes-dashboard/deploy.sh"
        ).read_text(encoding="utf-8")
        cls.manifest = (
            ROOT / "apps/kubernetes-dashboard/dashboard.yaml"
        ).read_text(encoding="utf-8")

    def test_dashboard_is_deployed_after_certs_before_application_secrets(self) -> None:
        certs = self.wizard.index('guided_run_and_verify certs "Certs"')
        dashboard = self.wizard.index('guided_run_and_verify dashboard "Dashboard"')
        secrets = self.wizard.index('guided_run_and_verify secrets "Secrets"')
        self.assertLess(certs, dashboard)
        self.assertLess(dashboard, secrets)

    def test_hostname_is_rendered_and_domain_is_validated(self) -> None:
        self.assertIn("${DASHBOARD_HOST}", self.manifest)
        self.assertNotIn("fortifydemo.com", self.manifest)
        self.assertIn("${DASHBOARD_NAMESPACE}", self.manifest)
        self.assertIn("${DASHBOARD_SERVICE}", self.manifest)
        self.assertIn("kubernetes-dashboard-kong-proxy", self.deploy)
        self.assertIn("envsubst '${DASHBOARD_HOST}", self.deploy)
        self.assertIn('Invalid DOMAIN for Dashboard ingress', self.deploy)

    def test_setup_is_idempotent_and_readiness_is_bounded(self) -> None:
        self.assertIn("microk8s enable dashboard", self.deploy)
        self.assertIn("--dry-run=client -o yaml", self.deploy)
        self.assertGreaterEqual(self.deploy.count('apply -f -'), 2)
        self.assertIn("rollout status deployment/kubernetes-dashboard", self.deploy)
        self.assertIn("app.kubernetes.io/instance=kubernetes-dashboard", self.deploy)
        self.assertIn("--timeout=300s", self.deploy)

    def test_tokens_are_short_lived_and_never_persisted(self) -> None:
        self.assertNotIn("service-account-token", self.manifest)
        self.assertNotIn("kind: Secret", self.manifest)
        self.assertNotIn("create token", self.deploy)
        self.assertIn(
            "create token fortify-dashboard-viewer --duration=1h", self.wizard
        )
        self.assertIn(
            "create token fortify-dashboard-admin --duration=1h", self.wizard
        )
        self.assertIn("view-only token (recommended)", self.wizard)
        self.assertIn("WARNING: administrator access", self.wizard)
        self.assertIn(
            'confirm "Generate a 1-hour cluster administrator token?"', self.wizard
        )

    def test_viewer_and_admin_permissions_are_distinct(self) -> None:
        self.assertIn("name: view", self.manifest)
        self.assertIn("name: cluster-admin", self.manifest)
        self.assertIn("name: fortify-dashboard-viewer", self.manifest)
        self.assertIn("name: fortify-dashboard-admin", self.manifest)

    def test_wizard_dns_guidance_includes_dashboard(self) -> None:
        helper = (ROOT / "scripts/lib/coredns-lab-hosts.sh").read_text(encoding="utf-8")
        self.assertIn("dashboard.$domain", helper)
        self.assertIn("expected_hosts=$(fortify_lab_hostnames_inline)", self.wizard)

    def test_token_workflow_repairs_missing_dashboard_resources(self) -> None:
        self.assertIn("ensure_dashboard_access()", self.wizard)
        self.assertIn("ensure_dashboard_access ||", self.wizard)
        self.assertIn("apps/kubernetes-dashboard/deploy.sh", self.wizard)
        for resource in (
            '"service/$dashboard_service"',
            "serviceaccount/fortify-dashboard-viewer",
            "serviceaccount/fortify-dashboard-admin",
            "ingress/ingress-dashboard",
        ):
            self.assertIn(resource, self.wizard)
        self.assertLess(
            self.wizard.index("ensure_dashboard_access ||"),
            self.wizard.index("create token fortify-dashboard-viewer"),
        )

    def test_persistent_tokens_are_explicit_recoverable_and_not_repo_stored(self) -> None:
        self.assertIn("Generate persistent view-only token", self.wizard)
        self.assertIn("Generate persistent administrator token", self.wizard)
        self.assertIn("Revoke persistent Dashboard tokens", self.wizard)
        self.assertIn("kubernetes.io/service-account-token", self.wizard)
        self.assertIn("Type PERSISTENT", self.wizard)
        self.assertIn("fortify-dashboard-viewer-persistent-token", self.wizard)
        self.assertIn("fortify-dashboard-admin-persistent-token", self.wizard)
        self.assertIn("--ignore-not-found", self.wizard)
        self.assertNotIn("persistent-token", self.manifest)
        self.assertIn("remain valid until revoked", self.wizard)

    def test_persistent_token_wait_is_bounded(self) -> None:
        self.assertIn('DASHBOARD_TOKEN_WAIT_SECONDS:-30', self.wizard)
        self.assertIn("did not populate", self.wizard)
        command = (
            'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; '
            'DASHBOARD_TOKEN_WAIT_SECONDS=1; '
            'KUBECTL=fake_kubectl; fake_kubectl() { return 1; }; '
            'dashboard_wait_for_persistent_token kube-system missing'
        )
        timed_out = subprocess.run(
            ["bash", "-c", command, "dashboard-test", str(ROOT / "start_wizard.sh")],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        self.assertNotEqual(timed_out.returncode, 0)
        self.assertIn("did not populate", timed_out.stderr)

        success = subprocess.run(
            [
                "bash", "-c",
                'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; '
                'KUBECTL=fake_kubectl; fake_kubectl() { printf ZmFrZQ==; }; '
                'dashboard_wait_for_persistent_token kube-system ready',
                "dashboard-test", str(ROOT / "start_wizard.sh"),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(success.returncode, 0, success.stderr)


if __name__ == "__main__":
    unittest.main()
