"""Contracts for the Phase 3.5 Python diagnostics engine."""

from __future__ import annotations

import tarfile
import tempfile
import unittest
from pathlib import Path

from fortifylab.core.command import CommandResult
from fortifylab.diagnostics import ClusterCollector, RouteCheck, image_pull_findings, route_findings, write_bundle
from fortifylab.diagnostics.registry import docker_auth_findings, regcred_findings


class PythonDiagnosticsEngineTests(unittest.TestCase):
    def test_cluster_collector_uses_read_only_kubectl_and_helm_commands(self) -> None:
        commands: list[tuple[str, ...]] = []

        def fake_runner(command: tuple[str, ...]) -> CommandResult:
            commands.append(command)
            return CommandResult(command, 0, "ok", "", 0.01)

        results = ClusterCollector(namespace="fortify", runner=fake_runner).collect()

        self.assertEqual(len(results), 8)
        self.assertTrue(all(result.ok for result in results))
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "pods", "-o", "wide"), commands)
        self.assertIn(("microk8s", "kubectl", "get", "nodes", "-o", "wide"), commands)
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "endpoints"), commands)
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "pvc"), commands)
        self.assertIn(("microk8s", "helm3", "-n", "fortify", "list"), commands)

    def test_route_findings_flag_dns_ingress_and_tls_problems(self) -> None:
        findings = route_findings(
            (
                RouteCheck(
                    host="ssc.fortifydemo.proxmox",
                    expected_ip="192.168.1.177",
                    resolved_ip="192.168.1.1",
                    ingress_present=False,
                    tls_secret_present=False,
                    http_status=404,
                    tls_common_name="TRAEFIK DEFAULT CERT",
                ),
            )
        )

        self.assertIn("ssc.fortifydemo.proxmox: DNS resolves to 192.168.1.1, expected 192.168.1.177.", findings)
        self.assertIn("ssc.fortifydemo.proxmox: matching ingress host is missing.", findings)
        self.assertIn("ssc.fortifydemo.proxmox: TLS secret is missing; Traefik may serve its default certificate.", findings)
        self.assertIn("ssc.fortifydemo.proxmox: served certificate is the Traefik default certificate.", findings)
        self.assertIn("ssc.fortifydemo.proxmox: route returned 404; ingress host or router matching may be wrong.", findings)

    def test_image_pull_findings_suggest_registry_refresh(self) -> None:
        findings = image_pull_findings(("Warning Failed pod/ssc-webapp-0 Error: ImagePullBackOff",))

        self.assertEqual(findings[0].resource, "pod/ssc-webapp-0")
        self.assertIn("refresh registry credentials", findings[0].message)

    def test_registry_auth_findings_report_missing_auth_without_values(self) -> None:
        self.assertIn("Docker auth config is missing", docker_auth_findings(None)[0])
        self.assertIn("regcred is missing", regcred_findings("Opaque")[0])
        self.assertEqual(docker_auth_findings('{"auths": {"registry.example": {}}}'), ())
        self.assertEqual(regcred_findings("kubernetes.io/dockerconfigjson"), ())

    def test_diagnostics_bundle_redacts_sensitive_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = write_bundle(
                Path(tmp),
                {
                    "cluster/pods.txt": "mysql-0 Running\n",
                    "env.txt": "DEFAULT_PASS=do-not-print\nDOMAIN=demo.test\n",
                },
            )

            with tarfile.open(bundle.path, "r:gz") as archive:
                env_text = archive.extractfile("env.txt").read().decode("utf-8")
                pods_text = archive.extractfile("cluster/pods.txt").read().decode("utf-8")
                metadata_text = archive.extractfile("metadata.json").read().decode("utf-8")

        self.assertIn("mysql-0 Running", pods_text)
        self.assertIn("<redacted sensitive diagnostic line>", env_text)
        self.assertNotIn("do-not-print", env_text)
        self.assertIn('"sanitized": true', metadata_text)


if __name__ == "__main__":
    unittest.main()
