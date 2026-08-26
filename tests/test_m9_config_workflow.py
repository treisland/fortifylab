"""M9.2 tests for the noninteractive Config TUI workflow.

The workflow must stay clone-safe: these tests use temporary ``.env`` files,
do not import Textual, and do not touch repository or lab state.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fortifylab.navigation import find_item
from fortifylab.tui import workflows


VALID_REQUIRED = (
    "export NAMESPACE='fortify'\n"
    "export DOMAIN='demo.internal'\n"
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
    "export DEFAULT_PASS='old-secret-value'\n"
    "export SCDAST_SSC_PASS='dast-api-secret'\n"
    "export FORTIFY_LICENSE_FILE='/tmp/private-license.license'\n"
    "export FORTIFY_TLS_MODE='mkcert'\n"
)


class M9ConfigWorkflowTests(unittest.TestCase):
    def test_configuration_menu_opens_real_config_workflow_screen(self) -> None:
        selected = find_item("main", "3")
        assert selected is not None

        result = workflows.dispatch_menu_item(selected)

        self.assertEqual(result.kind, "screen")
        self.assertIsNotNone(result.screen)
        assert result.screen is not None
        self.assertEqual(result.screen.id, "configuration_editor")
        self.assertIn("Config", result.screen.title)
        self.assertNotIn("placeholder", result.message.lower())
        self.assertNotIn("modeled; operation wiring starts", result.message)

    def test_render_shows_tui_facing_diagnostics_validation_and_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                VALID_REQUIRED.replace("demo.internal", "bad_domain", 1).replace("https://$SSC", "not-a-url", 1),
                encoding="utf-8",
            )

            screen = _build_config_workflow(env_path)
            screen.handle_key("d")
            rendered = screen.render()

            self.assertIn("Config diagnostics:", rendered)
            self.assertIn("Validation: invalid", rendered)
            self.assertIn("Findings:", rendered)
            self.assertIn("DOMAIN: hostname is invalid", rendered)
            self.assertIn("SSC_URL: URL must include http(s) scheme and host", rendered)
            self.assertIn("Credentials, users, and passwords", rendered)
            self.assertNotIn("old-secret-value", rendered)
            self.assertNotIn("dast-api-secret", rendered)
            self.assertNotIn("/tmp/private-license.license", rendered)

            screen.handle_key("v")
            validation = screen.render()

            self.assertIn("Config validation:", validation)
            self.assertIn("Result: invalid", validation)
            self.assertIn("DOMAIN: hostname is invalid", validation)
            self.assertNotIn("old-secret-value", validation)
            self.assertNotIn("dast-api-secret", validation)

    def test_derived_repair_preview_is_redacted_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            original = (
                VALID_REQUIRED.replace("ssc.$DOMAIN", "ssc.wrong.example", 1)
                .replace("https://$SSC", "https://ssc.wrong.example", 1)
                + "export API_TOKEN='super-secret-token'\n"
            )
            env_path.write_text(original, encoding="utf-8")

            screen = _build_config_workflow(env_path)
            result = screen.handle_key("p")
            preview = screen.render()

            self.assertIn("Rendered derived repair preview.", result.message)
            self.assertIn("Derived config repair preview", preview)
            self.assertIn("Planned changes:", preview)
            self.assertIn("SSC: ssc.wrong.example -> ssc.$DOMAIN", preview)
            self.assertIn("SSC_URL: https://ssc.wrong.example -> https://$SSC", preview)
            self.assertIn("Preview only: no changes written.", preview)
            self.assertNotIn("super-secret-token", preview)
            self.assertNotIn("old-secret-value", preview)
            self.assertNotIn("dast-api-secret", preview)
            self.assertEqual(env_path.read_text(encoding="utf-8"), original)
            self.assertFalse((Path(directory) / ".env.backups").exists())
            self.assertFalse((Path(directory) / ".env.rollback").exists())

    def test_repair_refuses_noninteractive_write_until_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            original = VALID_REQUIRED.replace("lim.$DOMAIN", "lim.wrong.example", 1)
            env_path.write_text(original, encoding="utf-8")

            screen = _build_config_workflow(env_path)
            refused = screen.handle_key("y")
            refused_render = screen.render()

            self.assertIn("Preview the derived repair before applying it.", refused.message)
            self.assertIn("explicit confirmation is required", refused_render)
            self.assertEqual(env_path.read_text(encoding="utf-8"), original)
            self.assertFalse((Path(directory) / ".env.backups").exists())

            previewed = screen.handle_key("p")

            self.assertIn("Rendered derived repair preview.", previewed.message)
            self.assertEqual(env_path.read_text(encoding="utf-8"), original)
            self.assertFalse((Path(directory) / ".env.backups").exists())

    def test_confirmed_repair_writes_only_temp_env_and_creates_recovery_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(VALID_REQUIRED.replace("dast.$DOMAIN", "dast.wrong.example", 1), encoding="utf-8")

            screen = _build_config_workflow(env_path)
            preview = screen.handle_key("p")
            preview_render = screen.render()
            applied = screen.handle_key("y")
            applied_render = screen.render()

            self.assertIn("Rendered derived repair preview.", preview.message)
            self.assertIn("Planned changes:", preview_render)
            self.assertIn("Applied derived repair", applied.message)
            self.assertIn("Applied", applied_render)
            updated = env_path.read_text(encoding="utf-8")
            self.assertIn('export SCDAST="dast.$DOMAIN"', updated)
            self.assertTrue((Path(directory) / ".env.backups").is_dir())
            self.assertTrue((Path(directory) / ".env.rollback").is_file())
            self.assertNotIn("old-secret-value", preview_render)
            self.assertNotIn("old-secret-value", applied_render)


def _build_config_workflow(env_path: Path):
    builder = getattr(workflows, "build_config_workflow", None)
    if builder is None:
        raise AssertionError("M9.2 requires fortifylab.tui.workflows.build_config_workflow(env_file=...)")
    return builder(env_file=env_path)


if __name__ == "__main__":
    unittest.main()
