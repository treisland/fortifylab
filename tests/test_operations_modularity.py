"""Architecture contracts for the modular Bash operations layer."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "scripts" / "wizard" / "operations.sh"
MODULE_DIRS = (
    ROOT / "scripts" / "wizard" / "operations",
    ROOT / "scripts" / "wizard" / "flight-plans",
)


class OperationsModularityTests(unittest.TestCase):
    def modules(self) -> list[Path]:
        return [path for directory in MODULE_DIRS for path in sorted(directory.glob("*.sh"))]

    def test_compatibility_loader_is_small_and_explicit(self) -> None:
        loader = LOADER.read_text(encoding="utf-8")
        self.assertLess(len(loader.splitlines()), 100)
        self.assertIn("source_wizard_operation_module()", loader)
        for module in self.modules():
            relative = module.relative_to(ROOT / "scripts" / "wizard").as_posix()
            self.assertEqual(loader.count(relative), 1)

    def test_modules_declare_contracts_and_source_guards(self) -> None:
        for module in self.modules():
            body = module.read_text(encoding="utf-8")
            with self.subTest(module=module.name):
                self.assertIn("# Module:", body)
                self.assertIn("# Responsibility:", body)
                self.assertIn("# Requires:", body)
                self.assertIn("# Exports:", body)
                self.assertIn("# Side effects:", body)
                self.assertIn("# Interactive:", body)
                header = "\n".join(body.splitlines()[:25])
                self.assertIn("_LOADED", header)
                self.assertIn("return 0", header)
                self.assertLessEqual(len(body.splitlines()), 500)

    def test_every_exported_function_has_one_owner(self) -> None:
        owners: dict[str, list[str]] = {}
        for module in self.modules():
            for name in re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)", module.read_text(encoding="utf-8"), re.MULTILINE):
                owners.setdefault(name, []).append(module.name)
        duplicates = {name: modules for name, modules in owners.items() if len(modules) > 1}
        self.assertFalse(duplicates, duplicates)
        self.assertEqual(len(owners), 213)

    def test_sourced_modules_do_not_change_global_shell_error_mode(self) -> None:
        for module in self.modules():
            body = module.read_text(encoding="utf-8")
            with self.subTest(module=module.name):
                self.assertNotIn("Warning: truncated output", body)
                self.assertNotIn("Total output lines:", body)
                self.assertNotIn("\ufeff", body)
                self.assertNotRegex(body, r"(?m)^\s*set\s+-[a-zA-Z]*e")
                self.assertNotRegex(body, r"(?m)^\s*exit(?:\s|$)")

    def test_sources_are_clean_utf8_without_mojibake(self) -> None:
        suspicious = ("Ã", "â€", "�")
        for module in (LOADER, *self.modules()):
            body = module.read_text(encoding="utf-8")
            with self.subTest(module=module.name):
                self.assertFalse(body.startswith("\ufeff"))
                self.assertFalse(any(marker in body for marker in suspicious))

    def test_failed_load_does_not_poison_loader_guard(self) -> None:
        command = r'''
            error() { :; }
            export FORTIFY_HOME_K8S="$1"
            source "$2"
            status=$?
            [[ $status -ne 0 ]]
            [[ -z ${FORTIFY_WIZARD_OPERATIONS_LOADED:-} ]]
        '''
        result = subprocess.run(
            ["bash", "-c", command, "module-failure-test", str(ROOT / "missing-root"), str(LOADER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_entrypoint_loads_operations_twice_without_executing_work(self) -> None:
        command = r'''
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            source "$FORTIFY_HOME_K8S/scripts/wizard/operations.sh"
            declare -F cluster_reachable >/dev/null
            declare -F lab_start_deployments >/dev/null
            declare -F flight_plan_versions_menu >/dev/null
            declare -F env_apply_updates >/dev/null
            declare -F prereqs_menu >/dev/null
        '''
        result = subprocess.run(
            ["bash", "-c", command, "module-load-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
