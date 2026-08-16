"""Contracts for mkcert/BYO TLS validation helpers."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/lib/tls.sh"


class TlsContractTests(unittest.TestCase):
    def run_bash(self, body: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f'source "$1"; {body}', "tls-test", str(HELPER)],
            check=False,
            capture_output=True,
            text=True,
        )

    def make_cert(self, directory: Path, san: str) -> tuple[Path, Path]:
        cert = directory / "tls.crt"
        key = directory / "tls.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=ssc.example.test",
                "-addext",
                f"subjectAltName={san}",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return cert, key

    def test_tls_mode_defaults_to_mkcert_and_rejects_unknown_values(self) -> None:
        default = self.run_bash("fortify_tls_mode")
        invalid = self.run_bash("FORTIFY_TLS_MODE=public fortify_tls_mode")
        byo = self.run_bash("FORTIFY_TLS_MODE=byo fortify_tls_mode")

        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(default.stdout.strip(), "mkcert")
        self.assertEqual(byo.stdout.strip(), "byo")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("Invalid FORTIFY_TLS_MODE", invalid.stderr)

    def test_wildcard_san_covers_lab_hosts_but_not_extra_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cert, _key = self.make_cert(Path(tmp), "DNS:*.example.test")
            ok = self.run_bash(
                f'fortify_tls_cert_covers_host "{cert}" ssc.example.test'
            )
            bad = self.run_bash(
                f'fortify_tls_cert_covers_host "{cert}" deep.ssc.example.test'
            )

        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertNotEqual(bad.returncode, 0)

    def test_byo_validation_checks_certificate_expiry(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("fortify_tls_validate_cert_not_expired", helper)
        self.assertIn("-checkend 0", helper)
        self.assertIn('fortify_tls_validate_cert_not_expired "FORTIFY_BYO_TLS_CERT"', helper)
        self.assertIn('fortify_tls_validate_cert_not_expired "FORTIFY_BYO_TLS_CA_CERT"', helper)

    def test_byo_validation_requires_key_match_and_required_sans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            cert, key = self.make_cert(
                tmpdir,
                "DNS:ssc.example.test,DNS:sast.example.test,DNS:dast.example.test,DNS:lim.example.test,DNS:dashboard.example.test",
            )
            other_key = tmpdir / "other.key"
            subprocess.run(
                ["openssl", "genrsa", "-out", str(other_key), "2048"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            valid = self.run_bash(
                f'DOMAIN=example.test; FORTIFY_BYO_TLS_CERT="{cert}"; '
                f'FORTIFY_BYO_TLS_KEY="{key}"; FORTIFY_BYO_TLS_CA_CERT="{cert}"; '
                "fortify_tls_validate_byo_inputs"
            )
            mismatch = self.run_bash(
                f'DOMAIN=example.test; FORTIFY_BYO_TLS_CERT="{cert}"; '
                f'FORTIFY_BYO_TLS_KEY="{other_key}"; FORTIFY_BYO_TLS_CA_CERT="{cert}"; '
                "fortify_tls_validate_byo_inputs"
            )

        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("do not match", mismatch.stderr)
        self.assertNotIn("PRIVATE KEY", mismatch.stdout + mismatch.stderr)


if __name__ == "__main__":
    unittest.main()
