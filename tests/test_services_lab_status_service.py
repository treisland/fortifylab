"""Unit tests for fortifylab.services.lab_status_service (#446 slice 6)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.lab_status_service import LabStatusService  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class EnvBackedChecksTests(unittest.TestCase):
    def test_env_file_exists_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LabStatusService(env_file=Path(directory) / ".env")
            self.assertFalse(service.env_file_exists())

    def test_env_file_exists_false_when_present_but_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("", encoding="utf-8")
            service = LabStatusService(env_file=env_file)
            self.assertFalse(service.env_file_exists())

    def test_hosts_and_urls_valid_true_for_well_formed_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            _write(
                env_file,
                "DOMAIN=example.com\n"
                "SSC=ssc.example.com\nLIM=lim.example.com\nSCDAST=dast.example.com\nSCSAST=sast.example.com\n"
                "SSC_URL=https://ssc.example.com\nLIM_URL=https://lim.example.com\n"
                "LIM_API_URL=https://lim.example.com/LIM.API\nSCDAST_URL=https://dast.example.com\n"
                "SCSAST_URL=https://sast.example.com\nSCSAST_CTRL_URL=https://sast.example.com/scancentral-ctrl/\n",
            )
            service = LabStatusService(env_file=env_file)
            self.assertTrue(service.hosts_and_urls_valid())

    def test_hosts_and_urls_valid_false_for_missing_domain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            _write(env_file, "SSC=ssc.example.com\n")
            service = LabStatusService(env_file=env_file)
            self.assertFalse(service.hosts_and_urls_valid())

    def test_profile_selected_reflects_env_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            _write(env_file, "FORTIFY_DEPLOYMENT_PROFILE=full_lab\n")
            service = LabStatusService(env_file=env_file)
            self.assertTrue(service.profile_selected())
            self.assertEqual(service.deployment_profile(), "full_lab")

    def test_profile_selected_false_when_unset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LabStatusService(env_file=Path(directory) / ".env")
            self.assertFalse(service.profile_selected())

    def test_license_ready_requires_nonempty_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            license_path = Path(directory) / "fortify.license"
            env_file = Path(directory) / ".env"
            _write(env_file, f"FORTIFY_LICENSE_FILE={license_path}\n")
            service = LabStatusService(env_file=env_file)
            self.assertFalse(service.license_ready())
            license_path.write_text("license-body", encoding="utf-8")
            self.assertTrue(service.license_ready())

    def test_tls_artifacts_exist_requires_all_four_files_nonempty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = {
                "SERVER_CERT": base / "tls.crt",
                "SERVER_KEY": base / "tls.key",
                "JVM_KEYSTORE": base / "keystore.jks",
                "TRUSTSTORE": base / "truststore",
            }
            env_file = base / ".env"
            _write(env_file, "\n".join(f"{key}={path}" for key, path in paths.items()) + "\n")
            service = LabStatusService(env_file=env_file)
            self.assertFalse(service.tls_artifacts_exist())
            for path in paths.values():
                path.write_text("x", encoding="utf-8")
            self.assertTrue(service.tls_artifacts_exist())

    def test_root_ca_exported_checks_the_fixed_repo_path_not_env_rootca_cert(self) -> None:
        # Regression test: this used to read .env's ROOTCA_CERT, but
        # Bash's setup_root_ca_exported() always checks a fixed path
        # ($FORTIFY_HOME_K8S/certs/rootCA.pem) regardless of ROOTCA_CERT.
        # A custom/unset ROOTCA_CERT must not affect this check at all.
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            env_file = repo_root / ".env"
            _write(env_file, "ROOTCA_CERT=/somewhere/else/not-checked.pem\n")
            service = LabStatusService(env_file=env_file, repo_root=repo_root)
            self.assertFalse(service.root_ca_exported())

            (repo_root / "certs").mkdir()
            (repo_root / "certs" / "rootCA.pem").write_text("cert-body", encoding="utf-8")
            self.assertTrue(service.root_ca_exported())

    def test_docker_auth_ready_requires_nonempty_docker_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            service = LabStatusService(env_file=Path(directory) / ".env", docker_config_path=config_path)
            self.assertFalse(service.docker_auth_ready())
            config_path.write_text("{}", encoding="utf-8")
            # docker_auth_ready() also requires the docker CLI to be on PATH;
            # skip the true-case assertion if this host has no docker binary.
            import shutil

            if shutil.which("docker") is not None:
                self.assertTrue(service.docker_auth_ready())

    def test_fcli_truststore_available_never_reads_a_password(self) -> None:
        # Guards the deliberate scope trim: this must only ever check file
        # existence, never invoke keytool with a password on argv.
        with tempfile.TemporaryDirectory() as directory:
            truststore = Path(directory) / "truststore"
            env_file = Path(directory) / ".env"
            _write(env_file, f"TRUSTSTORE={truststore}\n")
            service = LabStatusService(env_file=env_file, repo_root=Path(directory))
            self.assertFalse(service.fcli_truststore_available())
            truststore.write_text("x", encoding="utf-8")
            self.assertTrue(service.fcli_truststore_available())

    def test_fcli_truststore_available_checks_the_live_fcli_truststore_env_var_first(self) -> None:
        # Regression test: Bash's setup_fcli_trust_ready() checks the live
        # FCLI_TRUSTSTORE env var before .env's TRUSTSTORE -- this fallback
        # was missing entirely.
        with tempfile.TemporaryDirectory() as directory:
            live_truststore = Path(directory) / "live-truststore"
            live_truststore.write_text("x", encoding="utf-8")
            service = LabStatusService(env_file=Path(directory) / ".env", repo_root=Path(directory))
            with unittest.mock.patch.dict(os.environ, {"FCLI_TRUSTSTORE": str(live_truststore)}):
                self.assertTrue(service.fcli_truststore_available())

    def test_fcli_truststore_available_falls_back_to_the_fixed_repo_path(self) -> None:
        # Regression test: Bash's last fallback is a fixed path,
        # $FORTIFY_HOME_K8S/certs/truststore -- also missing entirely.
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            service = LabStatusService(env_file=repo_root / ".env", repo_root=repo_root)
            self.assertFalse(service.fcli_truststore_available())

            (repo_root / "certs").mkdir()
            (repo_root / "certs" / "truststore").write_text("x", encoding="utf-8")
            self.assertTrue(service.fcli_truststore_available())


class KubectlBackedChecksTests(unittest.TestCase):
    def test_regcred_exists_reflects_command_success(self) -> None:
        service = LabStatusService(runner=lambda args: CommandResult(args, 0, "regcred", "", 0.0))
        self.assertTrue(service.regcred_exists())

    def test_regcred_exists_false_on_command_failure(self) -> None:
        service = LabStatusService(runner=lambda args: CommandResult(args, 1, "", "not found", 0.0))
        self.assertFalse(service.regcred_exists())

    def test_cluster_reachable_reflects_command_success(self) -> None:
        service = LabStatusService(runner=lambda args: CommandResult(args, 0, "Kubernetes control plane", "", 0.0))
        self.assertTrue(service.cluster_reachable())

    def test_cluster_reachable_false_on_command_failure(self) -> None:
        service = LabStatusService(runner=lambda args: CommandResult(args, 1, "", "connection refused", 0.0))
        self.assertFalse(service.cluster_reachable())


class ReadinessAndScoreTests(unittest.TestCase):
    def test_readiness_returns_eleven_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LabStatusService(
                env_file=Path(directory) / ".env",
                runner=lambda args: CommandResult(args, 1, "", "", 0.0),
                docker_config_path=Path(directory) / "config.json",
            )
            self.assertEqual(len(service.readiness()), 11)

    def test_score_counts_ready_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LabStatusService(
                env_file=Path(directory) / ".env",
                runner=lambda args: CommandResult(args, 0, "present", "", 0.0),
                docker_config_path=Path(directory) / "config.json",
            )
            ready, total = service.score()
            self.assertEqual(total, 11)
            self.assertGreaterEqual(ready, 2)  # at least the two kubectl-backed checks

    def test_score_all_false_when_nothing_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LabStatusService(
                env_file=Path(directory) / ".env",
                runner=lambda args: CommandResult(args, 1, "", "", 0.0),
                docker_config_path=Path(directory) / "config.json",
            )
            ready, total = service.score()
            self.assertEqual(ready, 0)
            self.assertEqual(total, 11)


if __name__ == "__main__":
    unittest.main()
