"""M7 Bash wizard retirement and compatibility regression tests.

These tests describe the supported clone-safe surfaces that must remain after
the deprecated Bash wizard internals and preview ``src`` package are cleaned up.
They must not call Kubernetes, Helm, Docker, the network, or live lab scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fortifylab.help import HelpRegistry
from fortifylab.operations import list_operations
from fortifylab.runbooks import discover_runbooks, list_help_topics


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
    "export DEFAULT_PASS='change-me'\n"
    "export FORTIFY_LICENSE_FILE='secrets/input/fortify.license'\n"
    "export FORTIFY_TLS_MODE='mkcert'\n"
)

SRC_BLOCKER = r"""
import importlib.abc
import importlib.machinery
import os
from pathlib import Path
import sys

root = Path(os.environ["FORTIFYLAB_ROOT"]).resolve()
retired_src = root / "src"

class BlockRetiredSrc(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.origin:
            origin = Path(spec.origin).resolve()
            if origin.is_relative_to(retired_src):
                raise ImportError(f"{fullname} resolved through retired src package: {origin}")
        return spec

sys.meta_path.insert(0, BlockRetiredSrc())

from fortifylab.cli import main

raise SystemExit(main(sys.argv[1:]))
"""


class M7RetirementCliTests(unittest.TestCase):
    maxDiff = None

    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{ROOT / 'src'}"
        env["FORTIFYLAB_ROOT"] = str(ROOT)
        env["NO_COLOR"] = "1"
        env["FORTIFYLAB_TUI_TEST_MODE"] = "1"
        env["FORTIFYLAB_DIAGNOSTICS_TEST_MODE"] = "1"
        return subprocess.run(
            [*args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def run_fortifylab(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_command(str(ROOT / "bin" / "fortifylab"), *args)

    def run_with_src_blocker(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_command(sys.executable, "-c", SRC_BLOCKER, *args)

    def make_env_file(self) -> tempfile.NamedTemporaryFile:
        env_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        env_file.write(VALID_ENV)
        env_file.close()
        return env_file

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("retired src package", result.stdout + result.stderr)

    def test_supported_cli_entrypoints_do_not_import_deprecated_src_package(self) -> None:
        commands = (
            ("--help",),
            ("doctor", "--check"),
            ("status", "--check"),
            ("help", "topic", "guided/sast", "--check"),
            ("tui", "--check"),
        )

        for command in commands:
            with self.subTest(command=command):
                result = self.run_with_src_blocker(*command)
                self.assert_success(result)

    def test_config_cli_entrypoints_do_not_import_deprecated_src_package(self) -> None:
        env_file = self.make_env_file()
        try:
            commands = (
                ("config", "validate", "--env-file", env_file.name),
                ("config", "diagnostics", "--env-file", env_file.name),
            )
            for command in commands:
                with self.subTest(command=command):
                    result = self.run_with_src_blocker(*command)
                    self.assert_success(result)
        finally:
            Path(env_file.name).unlink(missing_ok=True)

    def test_start_wizard_shim_preserves_supported_commands(self) -> None:
        shim = ROOT / "start_wizard.sh"
        self.assertTrue(shim.is_file())
        self.assertTrue(os.access(shim, os.X_OK))

        result = self.run_command(str(shim), "--help")
        self.assert_success(result)
        self.assertIn("fortifylab", result.stdout.lower())

        for command, expected in (
            (("doctor", "--check"), "FortifyLab Doctor"),
            (("status", "--check"), "FortifyLab Status"),
            (("help", "topic", "guided/sast", "--check"), "ScanCentral SAST"),
            (("tui", "--check"), "FortifyLab Python TUI"),
        ):
            with self.subTest(command=command):
                result = self.run_command(str(shim), *command)
                self.assert_success(result)
                self.assertIn(expected, result.stdout)

    def test_start_wizard_config_diagnostics_alias_remains_supported(self) -> None:
        env_file = self.make_env_file()
        try:
            direct = self.run_fortifylab("config", "diagnostics", "--env-file", env_file.name)
            shim = self.run_command(str(ROOT / "start_wizard.sh"), "config-diagnostics", "--env-file", env_file.name)
        finally:
            Path(env_file.name).unlink(missing_ok=True)

        self.assert_success(direct)
        self.assert_success(shim)
        self.assertEqual(shim.stdout, direct.stdout)

    def test_regression_commands_are_clone_safe_and_noninteractive(self) -> None:
        env_file = self.make_env_file()
        try:
            commands = (
                (("doctor", "--check"), ("FortifyLab Doctor", "SKIP cluster.kubectl.client")),
                (("status", "--check"), ("FortifyLab Status", "components:")),
                (("help", "topic", "guided/sast", "--check"), ("ScanCentral SAST", "Offline help: docs/help/sast.txt")),
                (("config", "validate", "--env-file", env_file.name), ("Config validation:", "Result: valid")),
                (("config", "diagnostics", "--env-file", env_file.name), ("Config diagnostics:", "Validation: valid")),
                (("tui", "--check"), ("FortifyLab Python TUI", "Milestone: M2 navigation parity")),
            )
            for command, expected_lines in commands:
                with self.subTest(command=command):
                    result = self.run_fortifylab(*command)
                    self.assert_success(result)
                    for expected in expected_lines:
                        self.assertIn(expected, result.stdout)
        finally:
            Path(env_file.name).unlink(missing_ok=True)


class M7RetiredInternalsDiscoveryTests(unittest.TestCase):
    def test_retired_wizard_sources_are_removed_from_git(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "scripts/wizard"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_source_cleanup_lanes_remain_out_of_scope_for_this_branch(self) -> None:
        retained_paths = (
            ROOT / "src",
            ROOT / "tests" / "quarantine" / "python_preview",
        )

        for path in retained_paths:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.exists())

    def test_supported_catalogs_do_not_expose_retired_wizard_or_quarantine_paths(self) -> None:
        forbidden_parts = {
            "src",
            "scripts/wizard",
            "tests/quarantine",
            "tests/quarantine/python_preview",
            "tests/quarantine/bash_wizard_internal",
        }

        discovered_paths: set[str] = set()
        discovered_paths.update(str(runbook.path.relative_to(ROOT)) for runbook in discover_runbooks(ROOT / "runbooks"))
        discovered_paths.update(str(topic.offline_path) for topic in list_help_topics())
        discovered_paths.update(str(HelpRegistry.from_directory().lookup(topic.id).offline_path.relative_to(ROOT)) for topic in list_help_topics())
        for operation in list_operations():
            for command in operation.command_plan:
                discovered_paths.update(part for part in command.argv if part.endswith(".sh"))

        for path in sorted(discovered_paths):
            with self.subTest(path=path):
                self.assertFalse(any(path == part or path.startswith(f"{part}/") for part in forbidden_parts))

    def test_default_unittest_discovery_excludes_quarantined_preview_contracts(self) -> None:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test*.py")
        test_ids = tuple(_test_id(test) for test in _walk_suite(suite))

        self.assertTrue(test_ids)
        for test_id in test_ids:
            with self.subTest(test_id=test_id):
                self.assertNotIn("tests.quarantine", test_id)
                self.assertNotIn("python_preview", test_id)
                self.assertNotIn("bash_wizard_internal", test_id)

    def test_start_wizard_shim_has_no_legacy_wizard_dispatch(self) -> None:
        text = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        forbidden_markers = (
            "source_wizard_module",
            "main_menu",
            "scripts/wizard/menu.sh",
            "scripts/wizard/operations.sh",
            "scripts/wizard/guided.sh",
            "scripts/wizard/runbooks.sh",
        )

        self.assertIn("bin/fortifylab", text)
        self.assertIn("config-diagnostics", text)
        for marker in forbidden_markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)


def _walk_suite(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _walk_suite(item)
        else:
            yield item


def _test_id(test: unittest.case.TestCase) -> str:
    return test.id()


if __name__ == "__main__":
    unittest.main()
