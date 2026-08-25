"""M6 runbook and help contract tests.

These tests define Python-native runbook/help behavior without calling
Kubernetes, Helm, Docker, the network, or live lab scripts.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap
import unittest

from fortifylab.runbooks import (
    RequirementStatus,
    RunbookAction,
    RunbookExecutionScope,
    RunbookRisk,
    check_requirements,
    command_preview,
    discover_runbooks,
    get_help_topic,
    list_help_topics,
    parse_runbook_metadata,
    run_contract,
    script_preview,
)


ROOT = Path(__file__).resolve().parents[1]


class M6RunbookContractTests(unittest.TestCase):
    def make_runbook(self, root: Path, relative: str, body: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        return path

    def test_comment_metadata_model_matches_bash_runbook_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.make_runbook(
                root,
                "official/fcli/sample.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Sample
                # description: Sample runbook.
                # domain: Local lab: SSC
                # category: FCLI
                # risk: high
                # order: 20
                # requires: bash,fcli
                # params:
                #   - name: ssc_token
                #     description: Token supplied by the operator.
                #     required: true
                echo never-run-in-test
                """,
            )

            metadata = parse_runbook_metadata(path, runbook_root=root)

            self.assertIsNotNone(metadata)
            assert metadata is not None
            self.assertEqual(metadata.id, "official.fcli.sample")
            self.assertEqual(metadata.domain, "Local lab: SSC")
            self.assertEqual(metadata.category, "FCLI")
            self.assertEqual(metadata.risk, RunbookRisk.HIGH)
            self.assertEqual(metadata.requires, ("bash", "fcli"))
            self.assertEqual(metadata.parameters[0].env_name, "SSC_TOKEN")
            self.assertTrue(metadata.parameters[0].secret)

    def test_discovery_preserves_domain_source_category_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_runbook(
                root,
                "training/later.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Training Later
                # description: Later.
                # domain: FCLI
                # category: Workshop
                # risk: low
                # order: 30
                """,
            )
            self.make_runbook(
                root,
                "official/first.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Official First
                # description: First.
                # domain: FCLI
                # category: Workshop
                # risk: low
                # order: 10
                """,
            )

            names = tuple(item.name for item in discover_runbooks(root))

            self.assertEqual(names, ("Official First", "Training Later"))

    def test_preview_actions_are_clone_safe_and_run_is_environment_dependent(self) -> None:
        metadata = discover_runbooks(ROOT / "runbooks")[0]

        script = script_preview(metadata, max_lines=3)
        command = command_preview(metadata)
        run = run_contract(metadata)

        self.assertEqual(script.action, RunbookAction.PREVIEW_SCRIPT)
        self.assertTrue(script.clone_safe)
        self.assertEqual(command.scope, RunbookExecutionScope.CLONE_SAFE)
        self.assertIn("bash", command.command)
        self.assertEqual(run.action, RunbookAction.RUN)
        self.assertEqual(run.scope, RunbookExecutionScope.ENVIRONMENT_DEPENDENT)

    def test_requirement_checks_use_injected_availability_and_do_not_probe_host(self) -> None:
        checked: list[str] = []

        def fake_available(name: str) -> bool:
            checked.append(name)
            return name == "bash"

        results = check_requirements(("bash", "fcli"), available=fake_available)

        self.assertEqual(checked, ["bash", "fcli"])
        self.assertEqual(results[0].status, RequirementStatus.AVAILABLE)
        self.assertEqual(results[1].status, RequirementStatus.MISSING)


class M6HelpContractTests(unittest.TestCase):
    def test_help_topics_are_stable_clone_safe_offline_topics(self) -> None:
        topics = list_help_topics()
        ids = {topic.id for topic in topics}

        for expected in ("overview", "architecture", "ssc", "sast", "dast", "urls", "lab-scope"):
            self.assertIn(expected, ids)

        for topic in topics:
            with self.subTest(topic=topic.id):
                self.assertEqual(topic.scope, RunbookExecutionScope.CLONE_SAFE)
                self.assertFalse(str(topic.offline_path).startswith("/"))
                self.assertTrue((ROOT / topic.offline_path).is_file())
                self.assertNotIn("://", topic.online_route)

    def test_guided_and_troubleshooting_aliases_keep_navigation_topic_ids(self) -> None:
        guided = get_help_topic("guided/mysql")
        failure = get_help_topic("troubleshooting/pending-pods")

        self.assertEqual(guided.id, "guided/mysql")
        self.assertEqual(guided.offline_path, Path("docs/help/mysql.txt"))
        self.assertEqual(failure.id, "troubleshooting/pending-pods")
        self.assertEqual(failure.offline_path, Path("docs/help/architecture.txt"))


if __name__ == "__main__":
    unittest.main()
