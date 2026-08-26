"""M9.2 Configuration Editor TUI workflow tests.

These tests exercise the pure workflow model only. They use temporary .env
files and never mutate the repo-root .env.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fortifylab.navigation import find_item
from fortifylab.tui.config import ConfigEditorScreen, build_config_workflow
from fortifylab.tui.workflows import dispatch_menu_item


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


class M9ConfigTuiWorkflowTests(unittest.TestCase):
    def write_env(self, directory: str, content: str = VALID_ENV) -> Path:
        env_file = Path(directory) / ".env"
        env_file.write_text(content, encoding="utf-8")
        return env_file

    def test_configuration_menu_opens_registered_workflow_screen(self) -> None:
        selected = find_item("main", "3")
        assert selected is not None

        result = dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsInstance(result.screen, ConfigEditorScreen)
        assert result.screen is not None
        self.assertEqual(result.screen.id, "configuration_editor")
        self.assertIn("Configuration workflow", result.screen.render())

    def test_diagnostics_and_validation_render_redacted_tui_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(
                directory,
                VALID_ENV.replace("example.test", "bad_domain", 1).replace("super-secret", "", 1),
            )
            screen = build_config_workflow(env_file=env_file)

            diagnostics = screen.diagnostics()
            validation = screen.validate()

            self.assertIn("Config diagnostics:", diagnostics)
            self.assertIn("Validation: invalid", diagnostics)
            self.assertIn("Config validation:", validation)
            self.assertIn("Result: invalid", validation)
            self.assertIn("DOMAIN: hostname is invalid", validation)
            self.assertIn("DEFAULT_PASS: required value is missing", validation)
            self.assertNotIn("super-secret", diagnostics + validation)

    def test_derived_repair_preview_is_redacted_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)
            before = env_file.read_text(encoding="utf-8")
            screen = build_config_workflow(env_file=env_file)

            preview = screen.preview_repair()

            self.assertEqual(env_file.read_text(encoding="utf-8"), before)
            self.assertFalse((Path(directory) / ".env.backups").exists())
            self.assertIn("Derived config repair preview:", preview)
            self.assertIn("SSC: legacy.example.test -> ssc.$DOMAIN", preview)
            self.assertIn("SSC_URL: https://legacy.example.test -> https://$SSC", preview)
            self.assertIn("Preview only: no changes written.", preview)
            self.assertNotIn("super-secret", preview)

    def test_repair_requires_explicit_confirmation_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)
            before = env_file.read_text(encoding="utf-8")
            screen = build_config_workflow(env_file=env_file)

            result = screen.apply_repair(confirmed=False)

            self.assertEqual(env_file.read_text(encoding="utf-8"), before)
            self.assertFalse((Path(directory) / ".env.backups").exists())
            self.assertIn("explicit confirmation is required", result)

    def test_confirmed_repair_writes_temp_env_with_backup_and_rollback_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)
            screen = build_config_workflow(env_file=env_file)
            screen.preview_repair()

            result = screen.apply_repair(confirmed=True)

            repaired = env_file.read_text(encoding="utf-8")
            self.assertIn('export SSC="ssc.$DOMAIN"', repaired)
            self.assertIn('export SSC_URL="https://$SSC"', repaired)
            backups = list((Path(directory) / ".env.backups").glob("*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((Path(directory) / ".env.rollback").exists())
            self.assertIn("Applied", result)
            self.assertNotIn("super-secret", result)

    def test_key_flow_previews_then_confirms_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = self.write_env(directory, BROKEN_DERIVED_ENV)
            screen = build_config_workflow(env_file=env_file)

            premature = screen.handle_key("y")
            self.assertIn("Preview", premature.message)
            self.assertFalse((Path(directory) / ".env.backups").exists())

            preview = screen.handle_key("p")
            confirm = screen.handle_key("y")

            self.assertIn("preview", preview.message.lower())
            self.assertIn("Applied", confirm.message)
            self.assertTrue((Path(directory) / ".env.rollback").exists())


if __name__ == "__main__":
    unittest.main()
