"""Safety and completeness contracts for modular operational help."""

from __future__ import annotations

import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/lib/operational-help.sh"
DOCS = ROOT / "docs/operations"


class OperationalHelpTests(unittest.TestCase):
    def run_helper(self, body: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["bash", "-c", 'source "$1"; shift; eval "$*"', "operational-test", str(HELPER), body],
            check=False,
            capture_output=True,
            text=True,
            env=merged,
            timeout=10,
        )

    def test_plan_dependency_order(self) -> None:
        result = self.run_helper("operational_deployment_plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        positions = [result.stdout.index(name) for name in (
            "MicroK8s", "TLS certificates", "Dashboard", "Kubernetes Secrets",
            "MySQL and PostgreSQL", "SSC and LIM", "ScanCentral SAST",
            "DAST Core", "DAST scanner",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("does not install", result.stdout)

    def test_offline_microk8s_is_bounded_and_helpful(self) -> None:
        result = self.run_helper(
            "operational_environment_overview",
            {"FORTIFY_OPERATION_KUBECTL": "/definitely/missing/kubectl"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline", result.stdout.lower())
        self.assertIn("remain available", result.stdout)
        self.assertIn("Host capacity", result.stdout)
        self.assertIn("TLS certificate", result.stdout)

    def test_functions_do_not_contain_mutating_kubectl_verbs(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        forbidden = (" kubectl apply", " kubectl delete", " kubectl patch", " kubectl edit", " kubectl scale", " kubectl exec")
        for command in forbidden:
            with self.subTest(command=command):
                self.assertNotIn(command, helper)
        for verb in (" apply ", " delete ", " patch ", " scale "):
            self.assertNotIn(f"_operational_kubectl{verb}", helper)

    def test_sanitizer_redacts_credentials_and_sensitive_paths(self) -> None:
        result = self.run_helper(
            "printf '%s\\n' 'PASSWORD=hunter2 TOKEN: abc123 Bearer ey.secret /home/alice/private' | _operational_sanitize_stream"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for secret in ("hunter2", "abc123", "ey.secret", "/home/alice/private"):
            self.assertNotIn(secret, result.stdout)
        self.assertGreaterEqual(result.stdout.count("[REDACTED]"), 3)
        self.assertIn("[LOCAL_PATH]", result.stdout)

    def test_doctor_hosts_resolution_reports_missing_loopback_and_wrong_ip(self) -> None:
        result = self.run_helper(
            "DOMAIN=example.test; "
            "operational_node_ip() { printf '10.0.0.5'; }; "
            "getent() { "
            "case \"$2\" in "
            "ssc.example.test) printf '10.0.0.5 STREAM\\n' ;; "
            "sast.example.test) printf '10.0.0.9 STREAM\\n' ;; "
            "lim.example.test) printf '127.0.0.1 STREAM\\n' ;; "
            "*) return 2 ;; "
            "esac; "
            "}; "
            "operational_doctor_hosts_resolution"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SSC", result.stdout)
        self.assertIn("expected lab node IP: 10.0.0.5", result.stdout)
        self.assertIn("resolved", result.stdout)
        self.assertIn("loopback", result.stdout)
        self.assertIn("wrong-ip", result.stdout)
        self.assertIn("missing", result.stdout)
        self.assertIn("TRAEFIK DEFAULT CERT", result.stdout)

    def test_doctor_tls_identity_reports_traefik_default_cert(self) -> None:
        result = self.run_helper(
            "_operational_lab_hosts() { printf 'SSC|ssc.example.test|https://ssc.example.test\\n'; }; "
            "_operational_tls_certificate_metadata() { "
            "printf 'subject=CN = TRAEFIK DEFAULT CERT\\nissuer=CN = TRAEFIK DEFAULT CERT\\n'; "
            "}; "
            "operational_doctor_tls_identity"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wrong-ingress-default-cert", result.stdout)
        self.assertIn("TRAEFIK DEFAULT CERT", result.stdout)

    def test_doctor_coredns_drift_does_not_print_configmap_data(self) -> None:
        corefile_marker = "SECRET_CONFIGMAP_DATA_SHOULD_NOT_PRINT"
        result = self.run_helper(
            "DOMAIN=example.test; "
            "operational_cluster_available() { return 0; }; "
            "_operational_kubectl() { "
            "case \"$*\" in "
            "*readyReplicas*) printf 1 ;; "
            "*spec.replicas*) printf 1 ;; "
            "*configmap*coredns*) printf '.:53 { hosts { 10.0.0.5 ssc.example.test sast.example.test dast.example.test lim.example.test dashboard.example.test SECRET_CONFIGMAP_DATA_SHOULD_NOT_PRINT fallthrough } }' ;; "
            "*) return 1 ;; "
            "esac; "
            "}; "
            "operational_doctor_coredns_drift"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deployment: 1/1 ready", result.stdout)
        self.assertIn("drift: matches", result.stdout)
        self.assertIn("Corefile contents not displayed", result.stdout)
        self.assertNotIn(corefile_marker, result.stdout)
        self.assertNotIn("10.0.0.5", result.stdout)

    def test_doctor_ingress_and_endpoints_use_read_only_status(self) -> None:
        result = self.run_helper(
            "operational_cluster_available() { return 0; }; "
            "_operational_kubectl() { "
            "case \"$*\" in "
            "*ingressclass*) printf 'NAME CONTROLLER\\npublic k8s.io/ingress-nginx\\n' ;; "
            "*' get ingress '*) printf 'NAME CLASS HOSTS\\nssc-ingress public ssc.example.test\\n' ;; "
            "*' endpoints ssc-service '*) printf 'x\\nx\\n' ;; "
            "*' endpoints lim '*) true ;; "
            "*' endpoints sdast-core-scancentral-dast-core-api '*) printf 'x\\n' ;; "
            "*) return 1 ;; "
            "esac; "
            "}; "
            "operational_doctor_ingress; operational_doctor_service_endpoints"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ingress classes", result.stdout)
        self.assertIn("public k8s.io/ingress-nginx", result.stdout)
        self.assertIn("ssc-ingress", result.stdout)
        self.assertIn("SSC", result.stdout)
        self.assertIn("ready", result.stdout)
        self.assertIn("LIM", result.stdout)
        self.assertIn("empty", result.stdout)

    def test_doctor_http_status_is_status_only(self) -> None:
        result = self.run_helper(
            "DOMAIN=example.test; "
            "curl() { "
            "case \"$*\" in "
            "*ssc.example.test*) printf 401 ;; "
            "*dast.example.test*) printf 503 ;; "
            "*) printf 200 ;; "
            "esac; "
            "}; "
            "operational_doctor_http_status"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HTTP 401", result.stdout)
        self.assertIn("reachable", result.stdout)
        self.assertIn("HTTP 503", result.stdout)
        self.assertIn("server-error", result.stdout)
        self.assertNotIn("Internal Server Error", result.stdout)
        self.assertNotIn("--resolve", result.stdout)
        self.assertNotIn("--max-time", result.stdout)

    def test_doctor_compact_summary_is_secret_safe(self) -> None:
        result = self.run_helper(
            "operational_cluster_available() { return 0; }; "
            "operational_capacity_memory_gib() { printf 32; }; "
            "operational_capacity_disk_gib() { printf 100; }; "
            "_operational_endpoint_count() { printf 1; }; "
            "_operational_kubectl() { "
            "case \"$*\" in "
            "*statefulsets,deployments*) printf 'KIND NAME DESIRED READY\\nStatefulSet ssc-webapp 1 1\\n' ;; "
            "*) return 1 ;; "
            "esac; "
            "}; "
            "curl() { printf 200; }; "
            "PASSWORD=super-secret TOKEN=hidden operational_doctor_compact_health_summary"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Doctor summary", result.stdout)
        self.assertIn("cluster: reachable", result.stdout)
        self.assertIn("HTTP 200", result.stdout)
        self.assertIn("no obvious", result.stdout)
        self.assertNotIn("super-secret", result.stdout)
        self.assertNotIn("hidden", result.stdout)

    def test_doctor_reports_low_capacity_as_action_needed(self) -> None:
        result = self.run_helper(
            "operational_cluster_available() { return 0; }; "
            "operational_capacity_memory_gib() { printf 8; }; "
            "operational_capacity_disk_gib() { printf 20; }; "
            "_operational_endpoint_count() { printf 1; }; "
            "_operational_kubectl() { "
            "case \"$*\" in "
            "*statefulsets,deployments*) printf 'KIND NAME DESIRED READY\\nStatefulSet ssc-webapp 1 1\\n' ;; "
            "*) return 1 ;; "
            "esac; "
            "}; "
            "curl() { printf 200; }; "
            "operational_doctor_compact_health_summary"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host capacity", result.stdout)
        self.assertIn("warning: memory 8 GiB", result.stdout)
        self.assertIn("warning: free disk 20 GiB", result.stdout)
        self.assertIn("investigate unavailable", result.stdout)

    def test_offline_bundle_has_only_allowlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_helper(
                f"operational_create_diagnostics_bundle {directory!r}",
                {"FORTIFY_OPERATION_KUBECTL": "/definitely/missing/kubectl"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            bundle = Path(result.stdout.strip().splitlines()[-1])
            with tarfile.open(bundle, "r:gz") as archive:
                self.assertEqual(
                    sorted(archive.getnames()),
                    [
                        "README.txt",
                        "deployment-plan.txt",
                        "doctor-summary.txt",
                        "kubernetes-evidence.txt",
                        "network-diagnostics.txt",
                        "wizard-log-excerpt.txt",
                    ],
                )
                evidence = archive.extractfile("kubernetes-evidence.txt").read().decode()
                readme = archive.extractfile("README.txt").read().decode()
            self.assertIn("unavailable", evidence)
            self.assertIn("wizard log excerpt", readme)
            self.assertIn("pod/application logs", readme)

    def test_topics_and_docs_are_complete(self) -> None:
        expected_topics = (
            "failed-deploy", "pending-pods", "restarting-pods", "url", "tls",
            "database", "ssc", "sast", "dast", "dashboard", "license", "registry",
        )
        for topic in expected_topics:
            result = self.run_helper(f"operational_troubleshooting_topic {topic}")
            self.assertEqual(result.returncode, 0, topic)
            self.assertTrue(result.stdout.strip(), topic)
        expected_docs = {
            "deployment-and-lifecycle.md", "networking-and-tls.md", "troubleshooting.md",
            "secrets-and-licenses.md", "backup-and-recovery.md",
            "versions-and-compatibility.md", "diagnostics.md", "first-scan.md",
        }
        self.assertTrue(expected_docs.issubset({path.name for path in DOCS.glob("*.md")}))
        combined = "\n".join(path.read_text(encoding="utf-8") for path in DOCS.glob("*.md"))
        for phrase in ("LAB / DEMO USE ONLY", "not production", "first-scan", "Delete data", "diagnostics"):
            self.assertIn(phrase.lower(), combined.lower())

    def test_guides_are_allowlisted_and_render_offline(self) -> None:
        result = self.run_helper(
            "FORTIFY_HOME_K8S=$PWD; operational_render_guide first-scan"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("first-scan", result.stdout.lower())
        rejected = self.run_helper(
            "FORTIFY_HOME_K8S=$PWD; operational_render_guide ../../.env"
        )
        self.assertEqual(rejected.returncode, 2)

    def test_version_overview_prints_only_allowlisted_profile_identifiers(self) -> None:
        result = self.run_helper(
            "FORTIFY_SSC_CHART_VERSION=26.2.0-1; "
            "FORTIFY_SSC_IMAGE_TAG=26.2.0.0183; operational_version_overview"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FORTIFY_SSC_CHART_VERSION", result.stdout)
        self.assertIn("26.2.0-1", result.stdout)
        self.assertIn("MATCH", result.stdout)
        self.assertNotIn("PASSWORD", result.stdout)
        self.assertNotIn("TOKEN", result.stdout)


if __name__ == "__main__":
    unittest.main()
