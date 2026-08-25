"""M4 config CLI bridge tests.

These tests use temporary .env files only. They must not run Kubernetes, Helm,
Docker, network calls, or mutate real Fortify Lab state.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

VALID_ENV = (
    "export NAMESPACE='fortify'\n"
    "export DOMAIN='example.test'\n"
    "export SSC='ssc.$DOMAIN'\n"
    "export LIM='lim.$DOMAIN'\n"
    "export SCDAST='dast.$DOMAIN'\n"
    "export SCSAST='sast.$DOMAIN'\n"
    "export SSC_URL='https://$SSC'\n"
    "export LIM_URL='https://$LIM'\n"
    "export LIM_API_URL='https://$LIM/LIM.API'\n"
    "export SCDAST_URL='https://$SCDAST'\n"
    "export SCSAST_URL='https://$SCSAST'\n"
    "export SCSAST_CTRL_URL='https://$SCSAST/scancentral-ctrl/'\n"
    "export DEFAULT_PASS='super-secret'\n"
    "export FORTIFY_LICENSE_FILE='secrets/input/fortify.license'\n"
    "export FORTIFY_TLS_MODE='mkcert'\n"
)

BROKEN_DERIVED_ENV = VALID_ENV.replace("ssc.$DOMAIN", "legacy.example.test", 1).replace(
    "https://$SSC", "https://legacy.example.test", 1
)


class M4ConfigCliBridgeTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["NO_COLOR"] = "1"
        return subprocess.run(
            [str(ROOT / "bin" / "fortifylab"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def run_wizard(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["NO_COLOR"] = "1"
        return subprocess.run(
            [str(ROOT / "start_wizard.sh"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def write_env(self, directory: str, content: str = VALID_ENV) -> Path:
        env_file = Path(directory) / ".env"
        env_file.write_text(content, encoding="utf-8")
        return env_file

    def test_validate_succeeds_for_valid_temp_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory)

            result = self.run_cli("config", "validate", "--env-file", str(env_file))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Config validation:", result.stdout)
            self.assertIn("Result: valid", result.stdout)

    def test_validate_fails_with_redacted_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(
                directory,
                VALID_ENV.replace("example.test", "bad_domain", 1).replace("super-secret", "", 1),
            )

            result = self.run_cli("config", "validate", "--env-file", str(env_file))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Result: invalid", result.stdout)
            self.assertIn("DOMAIN: hostname is invalid", result.stdout)
            self.assertIn("DEFAULT_PASS: required value is missing", result.stdout)
            self.assertNotIn("super-secret", result.stdout)

    def test_diagnostics_is_read_only_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory)
            before = env_file.read_text(encoding="utf-8")

            result = self.run_cli("config", "diagnostics", "--env-file", str(env_file))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env_file.read_text(encoding="utf-8"), before)
            self.assertIn("Config diagnostics:", result.stdout)
            self.assertIn("DOMAIN: example.test", result.stdout)
            self.assertIn("Credentials, users, and passwords:", result.stdout)
            self.assertNotIn("super-secret", result.stdout)

    def test_repair_derived_dry_run_prints_diff_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)
            before = env_file.read_text(encoding="utf-8")

            result = self.run_cli("config", "repair-derived", "--env-file", str(env_file), "--dry-run")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env_file.read_text(encoding="utf-8"), before)
            self.assertFalse((Path(directory) / ".env.backups").exists())
            self.assertIn("Planned changes:", result.stdout)
            self.assertIn("SSC: legacy.example.test -> ssc.$DOMAIN", result.stdout)
            self.assertIn("Dry run: no changes written.", result.stdout)

    def test_repair_derived_requires_yes_when_noninteractive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)
            before = env_file.read_text(encoding="utf-8")

            result = self.run_cli("config", "repair-derived", "--env-file", str(env_file))

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(env_file.read_text(encoding="utf-8"), before)
            self.assertFalse((Path(directory) / ".env.backups").exists())
            self.assertIn("Refusing to write without --yes", result.stdout)

    def test_repair_derived_yes_writes_backup_and_rollback_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)

            result = self.run_cli("config", "repair-derived", "--env-file", str(env_file), "--yes")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            repaired = env_file.read_text(encoding="utf-8")
            self.assertIn('export SSC="ssc.$DOMAIN"', repaired)
            self.assertIn('export SSC_URL="https://$SSC"', repaired)
            backups = list((Path(directory) / ".env.backups").glob("*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((Path(directory) / ".env.rollback").exists())
            self.assertIn(str(backups[0]), (Path(directory) / ".env.rollback").read_text(encoding="utf-8"))
            self.assertIn("Applied", result.stdout)

    def test_start_wizard_config_diagnostics_alias_delegates_to_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory)

            result = self.run_wizard("config-diagnostics", "--env-file", str(env_file))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Config diagnostics:", result.stdout)
            self.assertIn("DOMAIN: example.test", result.stdout)


if __name__ == "__main__":
    unittest.main()
