"""Contracts for bounded, secret-safe component dependency gates."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/lib/dependency-health.sh"


class DependencyHealthTests(unittest.TestCase):
    def run_bash(self, body: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f'source "$1"; {body}', "health-test", str(HELPER)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_wait_succeeds_after_retry(self) -> None:
        result = self.run_bash(
            "FORTIFY_HEALTH_INTERVAL=0; attempts=0; "
            "probe() { attempts=$((attempts + 1)); [ \"$attempts\" -ge 2 ]; }; "
            "health_wait_for dependency 2 probe"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dependency is ready", result.stdout)

    def test_wait_times_out_with_sanitized_retry_message(self) -> None:
        result = self.run_bash(
            "FORTIFY_HEALTH_INTERVAL=0.05; probe() { return 1; }; "
            "health_wait_for database 1 probe"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("within 1s", result.stderr)
        self.assertIn("retry", result.stderr.lower())

    def test_consumers_enforce_their_dependencies_before_helm(self) -> None:
        contracts = {
            "apps/ssc/start.sh": "health_mysql_ready",
            "apps/scsast/start.sh": "health_ssc_ready",
            "apps/scdast/core/start.sh": "health_postgresql_ready",
            "apps/scdast/scanner/start.sh": "health_dast_core_ready",
        }
        for relative, gate in contracts.items():
            script = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(script=relative):
                self.assertLess(script.index(gate), script.index("microk8s helm"))

    def test_database_probes_are_authenticated_and_suppress_output(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn('MYSQL_ROOT_PASSWORD_FILE:-', helper)
        self.assertIn('password=${MYSQL_ROOT_PASSWORD:-}', helper)
        self.assertIn('MYSQL_PWD="$password"', helper)
        self.assertIn('PGPASSWORD="$(cat "$POSTGRES_POSTGRES_PASSWORD_FILE")"', helper)
        self.assertGreaterEqual(helper.count(">/dev/null 2>&1"), 3)

    def test_invalid_timeout_configuration_fails_closed(self) -> None:
        result = subprocess.run(
            [
                "bash", "-c",
                'FORTIFY_HEALTH_TIMEOUT=invalid; source "$1"',
                "health-test", str(HELPER),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr)

    def test_service_endpoints_and_ingress_host_are_required(self) -> None:
        endpoints = self.run_bash(
            "KUBECTL=fake_kubectl; NAMESPACE=fortify; "
            "fake_kubectl() { printf '10.1.2.3'; }; "
            "health_service_endpoints_ready ssc-service"
        )
        missing_endpoints = self.run_bash(
            "KUBECTL=fake_kubectl; NAMESPACE=fortify; "
            "fake_kubectl() { return 0; }; "
            "health_service_endpoints_ready ssc-service"
        )
        ingress = self.run_bash(
            "KUBECTL=fake_kubectl; NAMESPACE=fortify; "
            "fake_kubectl() { printf 'ssc.example.test lim.example.test'; }; "
            "health_ingress_host_ready ssc-ingress ssc.example.test"
        )
        wrong_ingress = self.run_bash(
            "KUBECTL=fake_kubectl; NAMESPACE=fortify; "
            "fake_kubectl() { printf 'other.example.test'; }; "
            "health_ingress_host_ready ssc-ingress ssc.example.test"
        )
        self.assertEqual(endpoints.returncode, 0, endpoints.stderr)
        self.assertNotEqual(missing_endpoints.returncode, 0)
        self.assertEqual(ingress.returncode, 0, ingress.stderr)
        self.assertNotEqual(wrong_ingress.returncode, 0)

    def test_http_probe_accepts_auth_response_but_rejects_server_error(self) -> None:
        accepted = self.run_bash(
            "curl() { printf 401; }; health_http_url https://ssc.example.test"
        )
        rejected = self.run_bash(
            "curl() { printf 503; }; health_http_url https://ssc.example.test"
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotEqual(rejected.returncode, 0)

    def test_http_detail_reports_server_errors_without_body(self) -> None:
        result = self.run_bash(
            "curl() { printf 500; }; health_http_detail https://ssc.example.test"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HTTP 500", result.stdout)
        self.assertIn("pod logs", result.stdout)
        self.assertNotIn("Internal Server Error", result.stdout)

    def test_http_status_uses_bounded_max_time_override(self) -> None:
        result = self.run_bash(
            "curl() { printf '%s\n' \"$*\" | grep -q -- '--max-time 3' && printf 200; }; "
            "FORTIFY_HEALTH_HTTP_MAX_TIME=3 health_http_url https://ssc.example.test"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dast_core_requires_postgresql_ssc_and_lim(self) -> None:
        script = (ROOT / "apps/scdast/core/start.sh").read_text(encoding="utf-8")
        positions = [
            script.index("health_postgresql_ready"),
            script.index("health_ssc_ready"),
            script.index("health_lim_ready"),
            script.index("microk8s helm"),
        ]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
