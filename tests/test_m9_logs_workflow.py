"""M9.5 clone-safe TUI logs workflow behavior tests.

The tests use temporary fixture files only. They do not call Kubernetes, Helm,
Docker, network services, or live FortifyLab log commands.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fortifylab.logging import LogSource
from fortifylab.navigation import find_item
from fortifylab.tui.logs import LogsWorkflowScreen, WizardLogWorkflowScreen
from fortifylab.tui.workflows import dispatch_menu_item


class M9LogsWorkflowTests(unittest.TestCase):
    def test_logs_and_wizard_log_menu_actions_open_workflow_screens(self) -> None:
        cases = (
            ("main", "4", LogsWorkflowScreen, "logs", "Logs"),
            ("more_tools", "11", LogsWorkflowScreen, "logs", "Logs"),
            ("more_tools", "19", WizardLogWorkflowScreen, "wizard_log", "Wizard log"),
        )

        for menu_id, key, screen_type, screen_id, title in cases:
            with self.subTest(menu_id=menu_id, key=key):
                selected = find_item(menu_id, key)
                assert selected is not None

                result = dispatch_menu_item(selected)

                self.assertEqual(result.kind, "screen")
                self.assertIsInstance(result.screen, screen_type)
                assert result.screen is not None
                self.assertEqual(result.screen.id, screen_id)
                self.assertEqual(result.screen.title, title)
                self.assertIn("Read-only", result.screen.render())

    def test_log_source_listing_supports_number_and_arrow_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ssc = root / "ssc.log"
            dast = root / "dast.log"
            ssc.write_text("ssc ready\n", encoding="utf-8")
            dast.write_text("dast ready\n", encoding="utf-8")
            screen = LogsWorkflowScreen(
                log_sources=(
                    LogSource("ssc", "SSC", ssc, "available", "SSC log is available."),
                    LogSource("dast", "DAST", dast, "available", "DAST log is available."),
                )
            )

            rendered = screen.render()
            self.assertIn("> 1. SSC [available]", rendered)
            self.assertIn("  2. DAST [available]", rendered)

            self.assertEqual(screen.handle_key("2").message, "Selected DAST.")
            self.assertIn("> 2. DAST [available]", screen.render())
            self.assertEqual(screen.handle_key("up").message, "Selected SSC.")
            self.assertEqual(screen.handle_key("down").message, "Selected DAST.")

    def test_missing_log_renders_unavailable_state_without_crashing(self) -> None:
        missing = LogSource("wizard_log", "Wizard log", None, "missing", "Wizard log has not been created yet.")
        screen = WizardLogWorkflowScreen(log_sources=(missing,))

        rendered = screen.render()
        self.assertIn("Wizard log [missing]", rendered)
        self.assertIn("Wizard log has not been created yet.", rendered)

        self.assertEqual(screen.handle_key("enter").message, "Refreshed Wizard log.")
        rendered = screen.render()
        self.assertIn("Wizard log: missing", rendered)
        self.assertIn("Wizard log has not been created yet.", rendered)

    def test_refresh_uses_bounded_tail_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab.log"
            path.write_text("\n".join(f"line-{index:03d}" for index in range(1, 101)), encoding="utf-8")
            screen = LogsWorkflowScreen(log_sources=(LogSource("lab", "Lab", path, "available"),))

            self.assertEqual(screen.handle_key("r").message, "Refreshed Lab.")
            rendered = screen.render()

            self.assertIn("line-021", rendered)
            self.assertIn("line-100", rendered)
            self.assertNotIn("line-001", rendered)

    def test_refresh_reloads_file_content_and_back_exits_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab.log"
            path.write_text("before\n", encoding="utf-8")
            screen = LogsWorkflowScreen(log_sources=(LogSource("lab", "Lab", path, "available"),))

            self.assertEqual(screen.handle_key("enter").message, "Refreshed Lab.")
            self.assertIn("before", screen.render())

            path.write_text("after\n", encoding="utf-8")
            self.assertEqual(screen.handle_key("r").message, "Refreshed Lab.")
            self.assertIn("after", screen.render())
            self.assertNotIn("before", screen.render())

            exit_result = screen.handle_key("back")
            self.assertEqual(exit_result.message, "Back to menu.")
            self.assertTrue(exit_result.exit_screen)

    def test_log_tail_redacts_secrets_bearer_tokens_and_sensitive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sensitive.log"
            path.write_text(
                "\n".join(
                    (
                        "password=hunter2",
                        "token: secret-token",
                        "Authorization: Bearer abc.def",
                        "loaded /home/tre/.ssh/github-treisland-agent",
                        "read /var/lib/rancher/k3s/server/token",
                        "safe line",
                    )
                ),
                encoding="utf-8",
            )
            screen = LogsWorkflowScreen(log_sources=(LogSource("sensitive", "Sensitive", path, "available"),))

            self.assertEqual(screen.handle_key("r").message, "Refreshed Sensitive.")
            rendered = screen.render()

            self.assertIn("password=<redacted>", rendered)
            self.assertIn("token=<redacted>", rendered)
            self.assertIn("Authorization: <redacted>", rendered)
            self.assertIn("<sensitive-path>", rendered)
            self.assertIn("safe line", rendered)
            self.assertNotIn("hunter2", rendered)
            self.assertNotIn("secret-token", rendered)
            self.assertNotIn("abc.def", rendered)
            self.assertNotIn("/home/tre/.ssh/github-treisland-agent", rendered)
            self.assertNotIn("/var/lib/rancher/k3s/server/token", rendered)


if __name__ == "__main__":
    unittest.main()
