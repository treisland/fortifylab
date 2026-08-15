"""Contracts for the persistent HTTPS FortifyLab web service foundation."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.config.repair import domain_url_updates, expected_host, expected_url  # noqa: E402
from fortifylab.web import WebConsoleApp, WebConsoleConfig  # noqa: E402


class WebServiceFoundationTests(unittest.TestCase):
    def run_module(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        return subprocess.run(
            [sys.executable, "-m", "fortifylab", *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_web_config_requires_tls_cert_and_key_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "tls.crt"
            cert.write_text("placeholder cert", encoding="utf-8")

            issues = WebConsoleConfig(tls_cert=cert).validate()

        self.assertIn("TLS serving requires both tls_cert and tls_key.", issues)

    def test_web_config_reports_tls_posture_without_secret_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "tls.crt"
            key = Path(directory) / "tls.key"
            cert.write_text("placeholder cert", encoding="utf-8")
            key.write_text("placeholder key", encoding="utf-8")
            app = WebConsoleApp(WebConsoleConfig(
                bind_host="0.0.0.0",
                port=8443,
                allow_lan=True,
                access_token="test-token",
                tls_cert=cert,
                tls_key=key,
                lab_host="lab.fortifydemo.proxmox",
            ))
            status, payload = app.api_response("/api/security/posture")

        self.assertEqual(status, 200)
        console = payload["console"]
        self.assertEqual(console["public_url"], "https://lab.fortifydemo.proxmox:8443")
        self.assertTrue(console["tls_enabled"])
        self.assertTrue(console["token_required"])
        self.assertNotIn("test-token", str(payload))
        self.assertNotIn("tls.key", str(payload))

    def test_cli_web_help_exposes_service_tls_flags(self) -> None:
        result = self.run_module("web", "serve", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ("--token-file", "--tls-cert", "--tls-key", "--lab-host", "--lab-url"):
            with self.subTest(flag=flag):
                self.assertIn(flag, result.stdout)

    def test_cli_web_check_reads_token_file_and_tls_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "web-token"
            cert = root / "tls.crt"
            key = root / "tls.key"
            token.write_text("secret-token\n", encoding="utf-8")
            cert.write_text("placeholder cert", encoding="utf-8")
            key.write_text("placeholder key", encoding="utf-8")

            result = self.run_module(
                "web",
                "--check",
                "--bind", "0.0.0.0",
                "--allow-lan",
                "--token-file", str(token),
                "--tls-cert", str(cert),
                "--tls-key", str(key),
                "--lab-host", "lab.fortifydemo.proxmox",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("web console check: 200", result.stdout)
        self.assertNotIn("secret-token", result.stdout)

    def test_service_template_and_wrapper_keep_runtime_configuration_external(self) -> None:
        unit = (ROOT / "scripts/systemd/fortifylab-web.service.in").read_text(encoding="utf-8")
        wrapper = (ROOT / "scripts/fortifylab-web-service.sh").read_text(encoding="utf-8")

        self.assertIn("ExecStart=%h/fortifylab/scripts/fortifylab-web-service.sh", unit)
        self.assertIn("EnvironmentFile=-%h/fortifylab/.env", unit)
        self.assertIn("--token-file", wrapper)
        self.assertIn("--tls-cert", wrapper)
        self.assertIn("--tls-key", wrapper)
        self.assertIn("FORTIFY_WEB_ENABLE_ACTIONS", wrapper)
        self.assertNotIn("--token ", unit)

    def test_env_and_repair_derive_lab_host_and_url(self) -> None:
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        updates = {update.key: update.value for update in domain_url_updates("fortifydemo.proxmox")}

        self.assertIn('export LAB_HOST="lab.$DOMAIN"', env_example)
        self.assertIn('export LAB_URL="https://$LAB_HOST:8443"', env_example)
        self.assertEqual(expected_host("LAB_HOST", "fortifydemo.proxmox"), "lab.fortifydemo.proxmox")
        self.assertEqual(expected_url("LAB_URL", "fortifydemo.proxmox"), "https://lab.fortifydemo.proxmox:8443")
        self.assertEqual(updates["LAB_HOST"], "lab.$DOMAIN")
        self.assertEqual(updates["LAB_URL"], "https://$LAB_HOST:8443")

    def test_tls_lab_hosts_include_web_console_host(self) -> None:
        result = subprocess.run(
            ["bash", "-lc", "source scripts/lib/tls.sh; DOMAIN=fortifydemo.proxmox fortify_tls_lab_hosts"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lab.fortifydemo.proxmox", result.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
