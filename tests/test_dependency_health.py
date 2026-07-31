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

    def test_http_probe_accepts_auth_response_but_rejects_server_error(self) -> None:
        accepted = self.run_bash(
            "curl() { printf 401; }; health_http_url https://ssc.example.test"
        )
        rejected = self.run_bash(
            "curl() { printf 503; }; health_http_url https://ssc.example.test"
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotEqual(rejected.returncode, 0)

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
