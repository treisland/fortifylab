"""M9.5 read-only log workflow contract tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fortifylab.logging import (
    DEFAULT_LOG_TAIL_LINES,
    LogSource,
    discover_log_sources,
    read_log_detail,
    read_log_tail,
    wizard_log_path,
)
from fortifylab.navigation import find_item
from fortifylab.tui.logs import LogsWorkflowScreen, WizardLogWorkflowScreen
from fortifylab.tui.workflows import dispatch_menu_item


class M9LogsContractTests(unittest.TestCase):
    def test_wizard_log_path_matches_legacy_state_home_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"

            path = wizard_log_path(env={"XDG_STATE_HOME": str(state), "HOME": str(Path(directory) / "home")})

            self.assertEqual(path, state / "fortify-lab" / "wizard.log")
            self.assertFalse(path.exists())

    def test_environment_log_file_must_be_absolute(self) -> None:
        with self.assertRaises(ValueError):
            wizard_log_path(env={"FORTIFY_WIZARD_LOG_FILE": "relative/wizard.log", "HOME": os.path.expanduser("~")})

        sources = discover_log_sources(env={"FORTIFY_WIZARD_LOG_FILE": "relative/wizard.log"})
        self.assertEqual(sources[0].availability, "unsafe")
        self.assertIn("absolute path", sources[0].detail)

    def test_discover_known_sources_reports_missing_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"

            sources = discover_log_sources(state_root=state)

            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].id, "wizard_log")
            self.assertEqual(sources[0].availability, "missing")
            self.assertEqual(sources[0].path, state / "fortify-lab" / "wizard.log")
            self.assertFalse((state / "fortify-lab").exists())

    def test_tail_read_is_bounded_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "wizard.log"
            log_file.write_text(
                "\n".join(
                    [
                        "line-1 password=hunter2",
                        "line-2 token: abc123",
                        "line-3 https://user:pass@example.test/path",
                    ]
                ),
                encoding="utf-8",
            )
            source = LogSource("wizard_log", "Wizard log", log_file, "available")

            result = read_log_tail(source, lines=2)

            self.assertEqual(result.requested_lines, 2)
            self.assertEqual(result.lines, ("line-2 token=<redacted>", "line-3 https://user:<redacted>@example.test/path"))
            self.assertNotIn("abc123", result.text)
            self.assertNotIn("hunter2", result.text)

    def test_detail_read_caps_requested_line_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "wizard.log"
            log_file.write_text("\n".join(f"line-{index}" for index in range(1100)), encoding="utf-8")
            source = LogSource("wizard_log", "Wizard log", log_file, "available")

            result = read_log_detail(source, lines=5000)

            self.assertEqual(result.requested_lines, 1000)
            self.assertEqual(len(result.lines), 1000)
            self.assertEqual(result.lines[0], "line-100")

    def test_unavailable_source_returns_clear_state_without_reading(self) -> None:
        source = LogSource("wizard_log", "Wizard log", None, "unsafe", "FORTIFY_WIZARD_LOG_FILE must be an absolute path.")

        result = read_log_tail(source)

        self.assertEqual(result.lines, ())
        self.assertIn("absolute path", result.message)

    def test_logs_and_wizard_log_navigation_dispatch_to_workflow_screens(self) -> None:
        for menu_id, key, screen_type in (
            ("main", "4", LogsWorkflowScreen),
            ("more_tools", "11", LogsWorkflowScreen),
            ("more_tools", "19", WizardLogWorkflowScreen),
        ):
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None

                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsInstance(result.screen, screen_type)
                assert result.screen is not None
                self.assertIn("Read-only", result.screen.render())

    def test_logs_workflow_refresh_uses_injected_sources_only(self) -> None:
        source = LogSource("wizard_log", "Wizard log", None, "missing", "fixture missing")
        screen = LogsWorkflowScreen(log_sources=(source,))

        self.assertEqual(screen.handle_key("r").message, "Refreshed Wizard log.")

        rendered = screen.render()
        self.assertIn("fixture missing", rendered)
        self.assertIn("Wizard log: missing", rendered)
        self.assertNotIn(str(Path.cwd() / ".local"), rendered)

    def test_default_tail_limit_matches_legacy_contract(self) -> None:
        self.assertEqual(DEFAULT_LOG_TAIL_LINES, 80)


if __name__ == "__main__":
    unittest.main()
