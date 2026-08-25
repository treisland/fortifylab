"""M7 compatibility tests for the retired Bash wizard entrypoint.

These tests cover only clone-safe shim behavior. They must not call
Kubernetes, Helm, Docker, the network, or live lab scripts.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

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


class M7EntrypointCompatibilityTests(unittest.TestCase):
    maxDiff = None

    def run_wizard(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["NO_COLOR"] = "1"
        env["FORTIFYLAB_TUI_TEST_MODE"] = "1"
        env["FORTIFYLAB_DIAGNOSTICS_TEST_MODE"] = "1"
        return subprocess.run(
            [str(ROOT / "start_wizard.sh"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def test_start_wizard_help_delegates_to_primary_cli_help(self) -> None:
        result = self.run_wizard("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: fortifylab", result.stdout)
        self.assertIn("tui", result.stdout)
        self.assertNotIn("scripts/wizard", result.stdout + result.stderr)

    def test_start_wizard_tui_check_uses_supported_python_tui_check(self) -> None:
        result = self.run_wizard("tui", "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FortifyLab Python TUI", result.stdout)
        self.assertIn("Compatibility: M1 placeholder/skeleton smoke contract retained", result.stdout)

    def test_config_diagnostics_alias_delegates_to_python_config_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(VALID_ENV, encoding="utf-8")

            result = self.run_wizard("config-diagnostics", "--env-file", str(env_file))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Config diagnostics:", result.stdout)
        self.assertIn("DOMAIN: example.test", result.stdout)
        self.assertNotIn("super-secret", result.stdout)

    def test_legacy_doctor_status_and_help_topic_aliases_are_clone_safe(self) -> None:
        cases = (
            (("doctor",), "FortifyLab Doctor"),
            (("status",), "FortifyLab Status"),
            (("help", "topic", "ssc"), "Offline help: docs/help/ssc.txt"),
        )

        for args, expected in cases:
            with self.subTest(args=args):
                result = self.run_wizard(*args)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("kubectl", result.stderr.lower())
                self.assertNotIn("helm", result.stderr.lower())

    def test_start_wizard_remains_a_minimal_exec_shim(self) -> None:
        text = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")

        forbidden_legacy_markers = (
            "source_wizard_module",
            "main_menu",
            "scripts/wizard/menu.sh",
            "scripts/wizard/operations.sh",
            "bootstrap_env",
        )
        for marker in forbidden_legacy_markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)
        self.assertIn('exec "$repo_root/bin/fortifylab"', text)


if __name__ == "__main__":
    unittest.main()
