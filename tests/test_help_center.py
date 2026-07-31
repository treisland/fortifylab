"""Contracts for the offline, read-only Help and Knowledge Center."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIZARD = ROOT / "start_wizard.sh"
HELP = (ROOT / "scripts/lib/help.sh").read_text(encoding="utf-8")


class HelpCenterTests(unittest.TestCase):
    def run_functions(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; '
                "title() { printf 'TITLE:%s\\n' \"$1\"; }; sleep() { :; }; " + body,
                "help-test",
                str(WIZARD),
            ],
            input=user_input,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_every_topic_maps_to_a_readable_document(self) -> None:
        result = self.run_functions(
            'for topic in "${HELP_TOPIC_ID[@]}"; do '
            'i=$(help_topic_index "$topic") || exit 10; '
            'test -r "$FORTIFY_HOME_K8S/docs/help/${HELP_TOPIC_FILE[$i]}" || exit 11; done'
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_guided_steps_have_context_sensitive_topic_mapping(self) -> None:
        expected = {
            "prereqs": "overview", "inputs": "overview", "preflight": "overview",
            "certs": "overview", "dashboard": "dashboard", "secrets": "overview",
            "mysql": "mysql", "postgresql": "postgresql", "ssc": "ssc",
            "lim": "lim", "sast": "sast", "dast": "dast", "configure": "urls",
        }
        for step, topic in expected.items():
            result = self.run_functions(f"help_guided_topic {step}")
            self.assertEqual(result.stdout.strip(), topic)

    def test_missing_document_is_actionable_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_functions(
                f'FORTIFY_HOME_K8S="{directory}"; help_render_topic overview'
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Help document is unavailable", result.stderr)
        self.assertIn("Reinstall or restore", result.stdout)

    def test_rendering_is_read_only(self) -> None:
        before = subprocess.check_output(
            ["sha256sum", *sorted(str(path) for path in (ROOT / "docs/help").glob("*.txt"))],
            text=True,
        )
        result = self.run_functions("help_render_topic architecture")
        after = subprocess.check_output(
            ["sha256sum", *sorted(str(path) for path in (ROOT / "docs/help").glob("*.txt"))],
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, after)
        renderer = HELP.split("help_render_topic()", 1)[1].split(
            "help_show_topic()", 1
        )[0]
        for mutator in ("kubectl", "helm", "curl", "cp ", "mv ", "rm "):
            self.assertNotIn(mutator, renderer)

    def test_menu_opens_topic_and_returns(self) -> None:
        result = self.run_functions("help_center", "1\n\nr\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TITLE:Help Center", result.stdout)
        self.assertIn("TITLE:Help — System overview", result.stdout)
        self.assertIn("FORTIFY LAB SYSTEM OVERVIEW", result.stdout)

    def test_unknown_topic_is_rejected(self) -> None:
        result = self.run_functions("help_render_topic nonexistent")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown help topic", result.stderr)


if __name__ == "__main__":
    unittest.main()
