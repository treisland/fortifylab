"""Contracts for the Phase 3.4 Python configuration engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fortifylab.config import (
    ConfigStore,
    EnvUpdate,
    apply_updates,
    domain_url_updates,
    parse_env_text,
    preview_changes,
    validate_hosts_and_urls,
)


class PythonConfigEngineTests(unittest.TestCase):
    def test_parse_and_apply_updates_preserves_comments_and_unknown_keys(self) -> None:
        document = parse_env_text('# keep\nexport DOMAIN="old.test"\nCUSTOM_FLAG=yes\n')

        updated = apply_updates(document, (EnvUpdate("DOMAIN", "new.test"), EnvUpdate("DEFAULT_PASS", "p@ss&word")))

        rendered = updated.render()
        self.assertIn("# keep", rendered)
        self.assertIn("CUSTOM_FLAG=yes", rendered)
        self.assertIn("export DOMAIN=new.test", rendered)
        self.assertIn("export DEFAULT_PASS='p@ss&word'", rendered)

    def test_secret_values_are_redacted_in_preview(self) -> None:
        document = parse_env_text('export DEFAULT_PASS="old-secret"\n')

        preview = "\n".join(preview_changes(document, (EnvUpdate("DEFAULT_PASS", "new-secret"),)))

        self.assertIn("DEFAULT_PASS", preview)
        self.assertIn("<redacted> -> <redacted>", preview)
        self.assertNotIn("old-secret", preview)
        self.assertNotIn("new-secret", preview)

    def test_domain_url_updates_render_expression_values(self) -> None:
        document = parse_env_text('export DOMAIN="old.test"\nexport SSC="bad"\n')

        updated = apply_updates(document, domain_url_updates("FortifyDemo.PROXMOX"))

        rendered = updated.render()
        self.assertIn("export DOMAIN=fortifydemo.proxmox", rendered)
        self.assertIn('export SSC="ssc.$DOMAIN"', rendered)
        self.assertIn('export SCSAST_CTRL_URL="https://$SCSAST/scancentral-ctrl/"', rendered)

    def test_validation_flags_placeholder_host_and_url_drift(self) -> None:
        document = parse_env_text(
            "\n".join(
                (
                    "DOMAIN=fortifydemo.com",
                    "SSC=LIM",
                    "LIM=lim.fortifydemo.com",
                    "SCDAST=dast.fortifydemo.com",
                    "SCSAST=sast.fortifydemo.com",
                    "SSC_URL=LIM_URL",
                    "LIM_URL=https://lim.fortifydemo.com",
                    "SCDAST_URL=https://dast.fortifydemo.com",
                    "SCSAST_URL=https://sast.fortifydemo.com",
                    "SCSAST_CTRL_URL=https://sast.fortifydemo.com/scancentral-ctrl/",
                )
            )
        )

        issues = validate_hosts_and_urls(document)

        self.assertIn("SSC is set to placeholder-like value LIM; expected ssc.fortifydemo.com.", issues)
        self.assertIn("SSC_URL is set to placeholder-like value LIM_URL; expected https://ssc.fortifydemo.com.", issues)

    def test_store_apply_creates_backup_metadata_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env"
            env_file.write_text('export DOMAIN="old.test"\n', encoding="utf-8")
            store = ConfigStore(env_file)

            backup = store.apply("wizard-test", (EnvUpdate("DOMAIN", "new.test"),))

            self.assertIsNotNone(backup)
            self.assertIn("export DOMAIN=new.test", env_file.read_text(encoding="utf-8"))
            self.assertIn(str(backup), (root / ".env.rollback").read_text(encoding="utf-8"))
            self.assertIn("changed_keys=DOMAIN", backup.with_suffix(".meta").read_text(encoding="utf-8"))
            restored = store.rollback_last()
            self.assertEqual(restored, backup)
            self.assertIn('export DOMAIN="old.test"', env_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
