"""M4 Python-native config engine tests.

These tests use only temporary files and in-memory document parsing. They must
not run Kubernetes, Helm, Docker, network calls, or real Fortify Lab state.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fortifylab.config import (
    ConfigChange,
    ConfigValidationError,
    EnvDocument,
    diff_preview,
    repair_domain_changes,
    validate_env_file,
    write_env_file,
)


VALID_REQUIRED = (
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
    "export DEFAULT_PASS='change-me'\n"
    "export FORTIFY_LICENSE_FILE='secrets/input/fortify.license'\n"
    "export FORTIFY_TLS_MODE='mkcert'\n"
)


class M4ConfigEngineTests(unittest.TestCase):
    def test_parser_preserves_comments_blank_lines_export_and_expressions(self) -> None:
        source = (
            "# Fortify Lab config\n"
            "\n"
            "export DOMAIN='example.test'\n"
            "export SSC=\"ssc.$DOMAIN\" # derived host\n"
            "DEFAULT_PASS='secret-value'\n"
        )

        document = EnvDocument.parse(source)
        staged = document.stage((ConfigChange("SSC", "ssc.$DOMAIN", expression=True),))

        self.assertEqual(document.render(), source)
        self.assertEqual(document.values()["SSC"], "ssc.$DOMAIN")
        self.assertEqual(staged.render(), source)

    def test_writer_preserves_file_shape_and_creates_backup_and_rollback_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "# header\n\n" + VALID_REQUIRED + "export FORTIFY_FLIGHT_PLAN='fortify-26.2'\n",
                encoding="utf-8",
            )

            result = write_env_file(
                env_path,
                (ConfigChange("FORTIFY_FLIGHT_PLAN", "fortify-26.3"),),
                reason="unit-test",
            )

            self.assertEqual(result.changed_keys, ("FORTIFY_FLIGHT_PLAN",))
            self.assertIsNotNone(result.backup)
            assert result.backup is not None
            self.assertTrue(result.backup.backup_path.exists())
            self.assertEqual(result.backup.backup_path.read_text(encoding="utf-8").splitlines()[0], "# header")
            self.assertEqual(result.backup.rollback_marker.read_text(encoding="utf-8").strip(), str(result.backup.backup_path))
            self.assertIn("reason=unit-test", result.backup.metadata_path.read_text(encoding="utf-8"))
            self.assertIn("changed_keys=FORTIFY_FLIGHT_PLAN", result.backup.metadata_path.read_text(encoding="utf-8"))
            self.assertIn("export FORTIFY_FLIGHT_PLAN='fortify-26.3'", env_path.read_text(encoding="utf-8"))

    def test_diff_preview_redacts_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(VALID_REQUIRED, encoding="utf-8")

            diff = diff_preview(env_path, (ConfigChange("DEFAULT_PASS", "new-secret"), ConfigChange("DOMAIN", "demo.test")))
            rendered = tuple(entry.render() for entry in diff)

            self.assertIn("DEFAULT_PASS: <redacted> -> <redacted>", rendered)
            self.assertIn("DOMAIN: example.test -> demo.test", rendered)
            self.assertNotIn("change-me", "\n".join(rendered))
            self.assertNotIn("new-secret", "\n".join(rendered))

    def test_validation_uses_schema_for_domain_url_enum_version_path_and_required_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                VALID_REQUIRED.replace("example.test", "bad_domain", 1)
                .replace("https://$SSC", "not-a-url", 1)
                .replace("mkcert", "invalid", 1)
                .replace("change-me", "", 1)
                + "export FORTIFY_SSC_IMAGE_TAG=' bad tag'\n"
                + "export FORTIFY_BYO_TLS_KEY='bad\x00path'\n",
                encoding="utf-8",
            )

            issues = validate_env_file(env_path)
            issue_keys = {issue.key for issue in issues}

            self.assertIn("DOMAIN", issue_keys)
            self.assertIn("SSC_URL", issue_keys)
            self.assertIn("FORTIFY_TLS_MODE", issue_keys)
            self.assertIn("DEFAULT_PASS", issue_keys)
            self.assertIn("FORTIFY_SSC_IMAGE_TAG", issue_keys)
            self.assertIn("FORTIFY_BYO_TLS_KEY", issue_keys)

    def test_invalid_updates_do_not_write_or_create_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            original = VALID_REQUIRED
            env_path.write_text(original, encoding="utf-8")

            with self.assertRaises(ConfigValidationError):
                write_env_file(env_path, (ConfigChange("DOMAIN", "invalid_domain"),), reason="bad-update")

            self.assertEqual(env_path.read_text(encoding="utf-8"), original)
            self.assertFalse((Path(directory) / ".env.backups").exists())
            self.assertFalse((Path(directory) / ".env.rollback").exists())

    def test_domain_repair_preserves_expression_style_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(VALID_REQUIRED.replace("example.test", "demo.internal", 1), encoding="utf-8")

            repairs = repair_domain_changes(env_path)
            repaired = EnvDocument.read(env_path).stage(repairs)

            self.assertEqual(repaired.values()["DOMAIN"], "demo.internal")
            self.assertEqual(repaired.values()["SSC"], "ssc.$DOMAIN")
            self.assertEqual(repaired.values()["LIM_API_URL"], "https://$LIM/LIM.API")
            self.assertIn('export SSC="ssc.$DOMAIN"', repaired.render())


if __name__ == "__main__":
    unittest.main()
