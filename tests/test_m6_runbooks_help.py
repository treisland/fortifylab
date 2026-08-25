"""M6 runbook and help contract tests.

These tests define Python-native runbook/help behavior for the TUI migration.
They must remain clone-safe: no Kubernetes, Helm, Docker, network, or live lab
requirements are allowed in default test paths. Implementation-dependent tests
skip until the M6 public APIs land.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from fortifylab.navigation.registry import get_menu


ROOT = Path(__file__).resolve().parents[1]


def require_attrs(module_name: str, *names: str):
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            raise unittest.SkipTest(f"{module_name} missing M6 contract module") from exc
        raise
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        raise unittest.SkipTest(f"{module_name} missing M6 contract symbols: {', '.join(missing)}")
    return tuple(getattr(module, name) for name in names)


def enum_value(enum_cls, name: str):
    try:
        return enum_cls[name]
    except (KeyError, TypeError):
        return getattr(enum_cls, name)


def write_runbook(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    path.chmod(0o755)
    return path


class M6RunbookDiscoveryTests(unittest.TestCase):
    def test_navigation_keeps_runbook_and_help_targets_in_existing_locations(self) -> None:
        main_targets = {item.key: item.action.target for item in get_menu("main").items}
        more_targets = {item.key: item.action.target for item in get_menu("more_tools").items}

        self.assertEqual(main_targets["?"], "help_center")
        self.assertEqual(more_targets["15"], "runbook_library")
        self.assertEqual(more_targets["17"], "help_center")

    def test_discover_runbooks_parses_fixture_metadata_and_ignores_unmarked_scripts(self) -> None:
        discover_runbooks, RunbookRisk, RunbookSource = require_attrs(
            "fortifylab.runbooks",
            "discover_runbooks",
            "RunbookRisk",
            "RunbookSource",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runbooks"
            marked = write_runbook(
                root / "official" / "fcli" / "10-show-context.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Show context
                # description: Prints the selected lab context without changing state.
                # category: Readiness
                # domain: SSC
                # risk: low
                # order: 10
                # requires: python3
                # - name: lab_name
                #   description: Human-readable lab name.
                #   default: local
                #   required: true
                printf 'context=%s\\n' "$LAB_NAME"
                """,
            )
            write_runbook(
                root / "training" / "ignore-me.sh",
                """
                #!/usr/bin/env bash
                echo not a FortifyLab runbook
                """,
            )

            runbooks = tuple(discover_runbooks(root=root))

        self.assertEqual(len(runbooks), 1)
        runbook = runbooks[0]
        self.assertEqual(runbook.name, "Show context")
        self.assertEqual(runbook.description, "Prints the selected lab context without changing state.")
        self.assertEqual(runbook.category, "Readiness")
        self.assertEqual(runbook.domain, "SSC")
        self.assertEqual(runbook.risk, enum_value(RunbookRisk, "LOW"))
        self.assertEqual(runbook.source, enum_value(RunbookSource, "OFFICIAL"))
        self.assertEqual(runbook.order, 10)
        self.assertEqual(runbook.path, marked)
        self.assertEqual(tuple(runbook.requires), ("python3",))
        self.assertEqual(tuple(param.name for param in runbook.parameters), ("lab_name",))
        self.assertTrue(runbook.parameters[0].required)

    def test_validate_runbook_reports_metadata_and_requirement_errors_with_injected_checker(self) -> None:
        validate_runbook, RequirementCheck = require_attrs(
            "fortifylab.runbooks",
            "validate_runbook",
            "RequirementCheck",
        )

        with tempfile.TemporaryDirectory() as tmp:
            runbook = write_runbook(
                Path(tmp) / "runbooks" / "local" / "bad.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Broken metadata
                # risk: moonshot
                # requires: imaginary-tool
                echo ok
                """,
            )

            def fake_requirement_checker(tools: tuple[str, ...]) -> tuple[object, ...]:
                self.assertEqual(tools, ("imaginary-tool",))
                return (
                    RequirementCheck(tool="imaginary-tool", available=False, detail="fixture says missing"),
                )

            report = validate_runbook(runbook, requirement_checker=fake_requirement_checker)

        self.assertFalse(report.ok)
        combined = "\n".join(report.errors)
        self.assertIn("description", combined)
        self.assertIn("risk", combined)
        self.assertIn("imaginary-tool", combined)


class M6RunbookExecutionTests(unittest.TestCase):
    def test_check_requirements_uses_injected_tool_lookup_only(self) -> None:
        check_requirements = require_attrs("fortifylab.runbooks", "check_requirements")[0]
        lookups: list[str] = []

        def fake_tool_lookup(tool: str) -> str | None:
            lookups.append(tool)
            return f"/fixture/bin/{tool}" if tool == "python3" else None

        checks = tuple(check_requirements(("python3", "fcli"), tool_lookup=fake_tool_lookup))

        self.assertEqual(lookups, ["python3", "fcli"])
        self.assertEqual([(check.tool, check.available) for check in checks], [("python3", True), ("fcli", False)])

    def test_preview_redacts_secret_parameters_and_does_not_execute_script(self) -> None:
        load_runbook, preview_runbook = require_attrs("fortifylab.runbooks", "load_runbook", "preview_runbook")

        with tempfile.TemporaryDirectory() as tmp:
            path = write_runbook(
                Path(tmp) / "runbooks" / "local" / "preview.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Preview only
                # description: Verifies previews are not execution.
                # risk: low
                # - name: api_token
                #   description: Sensitive API token.
                #   default: fixture-secret
                # - name: target_name
                #   description: Safe display value.
                #   default: local
                exit 99
                """,
            )
            runbook = load_runbook(path)
            preview = preview_runbook(runbook, parameters={"api_token": "fixture-secret", "target_name": "demo"})

        self.assertIn("API_TOKEN=<redacted>", preview.command_text)
        self.assertIn("TARGET_NAME=demo", preview.command_text)
        self.assertIn("bash", preview.command_text)
        self.assertNotIn("fixture-secret", preview.command_text)
        self.assertEqual(preview.exit_code, None)

    def test_runner_refuses_unconfirmed_high_risk_runbook(self) -> None:
        load_runbook, run_runbook, RunbookConfirmationRequired = require_attrs(
            "fortifylab.runbooks",
            "load_runbook",
            "run_runbook",
            "RunbookConfirmationRequired",
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = write_runbook(
                Path(tmp) / "runbooks" / "local" / "needs-confirmation.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Needs confirmation
                # description: High risk fixture that must not run unconfirmed.
                # risk: high
                echo should-not-run
                """,
            )
            runbook = load_runbook(path)

            with self.assertRaises(RunbookConfirmationRequired):
                run_runbook(runbook, confirmed=False)

    def test_runner_executes_harmless_confirmed_runbook_with_injected_executor(self) -> None:
        load_runbook, run_runbook, RunbookCommandResult = require_attrs(
            "fortifylab.runbooks",
            "load_runbook",
            "run_runbook",
            "RunbookCommandResult",
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = write_runbook(
                Path(tmp) / "runbooks" / "local" / "harmless.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Harmless
                # description: Runs through an injected executor only.
                # risk: low
                # - name: api_token
                #   description: Secret token to redact.
                echo "token=$API_TOKEN"
                """,
            )
            runbook = load_runbook(path)
            captured_env: dict[str, str] = {}

            def fake_executor(command: tuple[str, ...], *, cwd: Path, env: dict[str, str]) -> object:
                self.assertEqual(command, ("bash", str(path)))
                self.assertEqual(cwd, Path(tmp))
                captured_env.update(env)
                return RunbookCommandResult(
                    command=command,
                    exit_code=0,
                    stdout="token=fixture-secret\nok\n",
                    stderr="",
                    duration_seconds=0.01,
                )

            result = run_runbook(
                runbook,
                parameters={"api_token": "fixture-secret"},
                confirmed=True,
                cwd=Path(tmp),
                executor=fake_executor,
            )

        self.assertTrue(result.ok)
        self.assertEqual(captured_env["API_TOKEN"], "fixture-secret")
        self.assertIn("token=<redacted>", result.stdout)
        self.assertNotIn("fixture-secret", result.stdout + result.stderr)


class M6HelpTopicTests(unittest.TestCase):
    def test_help_registry_loads_offline_topics_and_lookup_aliases_without_network(self) -> None:
        HelpRegistry = require_attrs("fortifylab.help", "HelpRegistry")[0]

        registry = HelpRegistry.from_directory(ROOT / "docs" / "help")
        topic = registry.lookup("ssc")
        guided = registry.lookup("guided/sast")
        alias = registry.lookup_alias("sast_controller")

        self.assertEqual(topic.id, "ssc")
        self.assertEqual(topic.title, "Software Security Center (SSC)")
        self.assertIn("docs/help/ssc.txt", topic.offline_path.as_posix())
        self.assertIn("SSC", topic.body)
        self.assertEqual(guided.id, "guided/sast")
        self.assertEqual(alias.id, "guided/sast")
        self.assertFalse(topic.requires_network)

    def test_unknown_help_topic_is_a_typed_lookup_error(self) -> None:
        HelpRegistry, HelpTopicNotFound = require_attrs("fortifylab.help", "HelpRegistry", "HelpTopicNotFound")

        registry = HelpRegistry.from_directory(ROOT / "docs" / "help")

        with self.assertRaises(HelpTopicNotFound):
            registry.lookup("does-not-exist")

    def test_cli_help_topic_check_is_deterministic_and_offline_when_available(self) -> None:
        require_attrs("fortifylab.help", "HelpRegistry")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["NO_COLOR"] = "1"
        result = __import__("subprocess").run(
            [str(ROOT / "bin" / "fortifylab"), "help", "topic", "ssc", "--check"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

        if result.returncode == 2 and "invalid choice" in result.stderr:
            raise unittest.SkipTest("fortifylab help topic CLI is not implemented yet")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Software Security Center", result.stdout)
        self.assertNotIn("http://", result.stdout)
        self.assertNotIn("https://", result.stdout)


if __name__ == "__main__":
    unittest.main()
