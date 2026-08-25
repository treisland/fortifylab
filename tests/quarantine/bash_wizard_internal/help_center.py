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
            "prereqs": "guided/prerequisites", "inputs": "guided/inputs",
            "preflight": "guided/preflight", "certs": "guided/tls",
            "dashboard": "guided/dashboard", "secrets": "guided/secrets",
            "mysql": "guided/mysql", "postgresql": "guided/postgresql",
            "ssc": "guided/ssc", "lim": "guided/lim", "sast": "guided/sast",
            "dast": "guided/dast", "configure": "guided/configuration",
        }
        for step, topic in expected.items():
            result = self.run_functions(f"help_guided_topic {step}")
            self.assertEqual(result.stdout.strip(), topic)

    def test_every_guided_step_and_failure_has_a_registered_topic(self) -> None:
        result = self.run_functions(
            'for step in "${GUIDED_STEP_ID[@]}"; do '
            'topic=$(help_guided_topic "$step") || exit 10; '
            'help_topic_index "$topic" >/dev/null || exit 11; done; '
            'for failure in failed-deploy pending-pods restarting-pods url tls database '
            'ssc sast dast dashboard license registry; do '
            'topic=$(help_failure_topic "$failure") || exit 12; '
            'help_topic_index "$topic" >/dev/null || exit 13; done'
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_topic_registry_columns_are_complete(self) -> None:
        result = self.run_functions(
            'test "${#HELP_TOPIC_ID[@]}" -eq "${#HELP_TOPIC_FILE[@]}" && '
            'test "${#HELP_TOPIC_ID[@]}" -eq "${#HELP_TOPIC_ROUTE[@]}" && '
            'for route in "${HELP_TOPIC_ROUTE[@]}"; do test -n "$route" || exit 14; done'
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_online_url_uses_one_configurable_base_without_network_access(self) -> None:
        result = self.run_functions(
            'FORTIFY_DOCS_BASE_URL=https://docs.example.test/lab/; '
            'help_topic_online_url guided/mysql'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "https://docs.example.test/lab/fortify/mysql/")
        self.assertNotIn("curl", HELP.split("help_topic_online_url()", 1)[1].split("help_render_topic()", 1)[0])

    def test_invalid_online_base_is_rejected(self) -> None:
        result = self.run_functions(
            'FORTIFY_DOCS_BASE_URL=/sensitive/local/path; help_topic_online_url guided/mysql'
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("/sensitive/local/path", result.stdout)

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
