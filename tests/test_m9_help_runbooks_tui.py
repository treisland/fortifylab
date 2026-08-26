"""M9.1 Help/Runbooks TUI workflow model tests.

These tests intentionally exercise clone-safe, noninteractive screen-model
behavior. They do not import Textual and they do not execute runbooks.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import textwrap
import unittest

from fortifylab.runbooks import RunbookAction, RunbookExecutionScope
from fortifylab.tui import workflows


ROOT = Path(__file__).resolve().parents[1]


def write_runbook(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    path.chmod(0o755)
    return path


def require_public(name: str):
    value = getattr(workflows, name, None)
    if value is None:
        raise AssertionError(f"fortifylab.tui.workflows must expose {name}() for pure TUI workflow tests")
    return value


def require_model_factory(factory_name: str, module_name: str, class_name: str):
    factory = getattr(workflows, factory_name, None)
    if callable(factory):
        return factory
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            module = None
        else:
            raise
    if module is not None:
        cls = getattr(module, class_name, None)
        if cls is not None:
            return cls
    raise AssertionError(
        f"Help/Runbooks TUI must expose {factory_name}() or {module_name}.{class_name} "
        "as a pure workflow model"
    )


def call_first(target: object, names: tuple[str, ...], *args, **kwargs):
    for name in names:
        value = getattr(target, name, None)
        if callable(value):
            return value(*args, **kwargs)
    joined = ", ".join(names)
    raise AssertionError(f"{target!r} must expose one of: {joined}")


def attr_first(target: object, names: tuple[str, ...]):
    for name in names:
        if hasattr(target, name):
            value = getattr(target, name)
            return value() if callable(value) and name.startswith("get_") else value
    joined = ", ".join(names)
    raise AssertionError(f"{target!r} must expose one of: {joined}")


def text_of(value: object) -> str:
    if value is None:
        return ""
    render = getattr(value, "render", None)
    if callable(render):
        return str(render())
    if isinstance(value, (list, tuple)):
        return "\n".join(text_of(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {text_of(item)}" for key, item in value.items())
    if hasattr(value, "__dict__"):
        return "\n".join(f"{key}: {text_of(item)}" for key, item in vars(value).items())
    return str(value)


def ids_from(records: object) -> set[str]:
    values = records.values() if isinstance(records, dict) else records
    found: set[str] = set()
    for item in values:
        topic_id = getattr(item, "id", None) or getattr(item, "topic_id", None)
        if topic_id:
            found.add(str(topic_id))
    return found


class M9HelpTuiWorkflowTests(unittest.TestCase):
    def make_help_model(self) -> object:
        factory = require_model_factory("build_help_workflow", "fortifylab.tui.help_runbooks", "HelpCenterScreen")
        try:
            return factory(help_root=ROOT / "docs" / "help")
        except TypeError:
            try:
                return factory(ROOT / "docs" / "help")
            except TypeError:
                return factory()

    def test_help_topic_listing_opens_detail_and_back_returns_to_listing(self) -> None:
        model = self.make_help_model()

        listing = call_first(model, ("list_topics", "topics", "topic_listing", "listing"))
        topic_ids = ids_from(listing)
        self.assertIn("overview", topic_ids)
        self.assertIn("ssc", topic_ids)
        listing_text = text_of(listing)
        self.assertIn("System overview", listing_text)
        self.assertIn("Software Security Center", listing_text)

        detail = call_first(model, ("open_topic", "select_topic", "show_topic", "topic_detail"), "ssc")
        detail_text = text_of(detail or attr_first(model, ("current_screen", "screen", "selected_topic")))
        self.assertIn("Software Security Center", detail_text)
        self.assertIn("SSC", detail_text)
        self.assertNotIn("http://", detail_text)
        self.assertNotIn("https://", detail_text)

        returned = call_first(model, ("back", "go_back", "return_to_listing"))
        returned_text = text_of(returned or attr_first(model, ("current_screen", "screen", "listing")))
        self.assertIn("System overview", returned_text)
        self.assertIn("Software Security Center", returned_text)

    def test_help_unknown_topic_is_rejected_without_changing_listing(self) -> None:
        model = self.make_help_model()
        before = text_of(call_first(model, ("list_topics", "topics", "topic_listing", "listing")))

        with self.assertRaises((KeyError, LookupError, ValueError)):
            call_first(model, ("open_topic", "select_topic", "show_topic", "topic_detail"), "missing/topic")

        after = text_of(call_first(model, ("list_topics", "topics", "topic_listing", "listing")))
        self.assertEqual(after, before)


class M9RunbooksTuiWorkflowTests(unittest.TestCase):
    def make_runbook_root(self, base: Path) -> tuple[Path, Path]:
        root = base / "runbooks"
        safe = write_runbook(
            root / "official" / "fcli" / "10-fixture-readiness.sh",
            """
            #!/usr/bin/env bash
            # fortifylab-runbook: true
            # name: Fixture readiness
            # description: Shows readiness context without changing state.
            # domain: SSC
            # category: Readiness
            # risk: low
            # order: 10
            # - name: lab_name
            #   description: Lab display name.
            #   default: local
            printf 'lab=%s\\n' "$LAB_NAME"
            """,
        )
        mutating = write_runbook(
            root / "local" / "99-mutating-fixture.sh",
            f"""
            #!/usr/bin/env bash
            # fortifylab-runbook: true
            # name: Mutating fixture
            # description: Would mutate state if a preview accidentally executed it.
            # domain: SSC
            # category: Guardrails
            # risk: high
            # order: 99
            touch {base / "should-not-exist"}
            """,
        )
        write_runbook(
            root / "training" / "not-a-runbook.sh",
            """
            #!/usr/bin/env bash
            echo ignored
            """,
        )
        return root, mutating

    def make_runbook_model(self, root: Path) -> object:
        factory = require_model_factory("build_runbook_workflow", "fortifylab.tui.help_runbooks", "RunbookLibraryScreen")
        try:
            return factory(runbook_root=root)
        except TypeError:
            return factory(root)

    def test_runbook_listing_detail_and_back_use_fixture_runbooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, _mutating = self.make_runbook_root(Path(tmp))
            model = self.make_runbook_model(root)

            listing = call_first(model, ("list_runbooks", "runbooks", "runbook_listing", "listing"))
            listing_text = text_of(listing)
            self.assertIn("Fixture readiness", listing_text)
            self.assertIn("Mutating fixture", listing_text)
            self.assertNotIn("not-a-runbook", listing_text)
            self.assertLess(listing_text.index("Fixture readiness"), listing_text.index("Mutating fixture"))

            detail = call_first(
                model,
                ("open_runbook", "select_runbook", "show_runbook", "runbook_detail"),
                "official.fcli.10-fixture-readiness",
            )
            detail_text = text_of(detail or attr_first(model, ("current_screen", "screen", "selected_runbook")))
            self.assertIn("Shows readiness context", detail_text)
            self.assertIn("Readiness", detail_text)
            self.assertIn("low", detail_text.lower())

            returned = call_first(model, ("back", "go_back", "return_to_listing"))
            returned_text = text_of(returned or attr_first(model, ("current_screen", "screen", "listing")))
            self.assertIn("Fixture readiness", returned_text)
            self.assertIn("Mutating fixture", returned_text)

    def test_runbook_preview_is_clone_safe_and_does_not_execute_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, mutating = self.make_runbook_root(base)
            marker = base / "should-not-exist"
            model = self.make_runbook_model(root)

            call_first(model, ("open_runbook", "select_runbook", "show_runbook", "runbook_detail"), "local.99-mutating-fixture")
            preview = call_first(model, ("preview_runbook", "preview", "preview_selected", "preview_command"))
            preview_text = text_of(preview)

            self.assertFalse(marker.exists(), "preview/open must not execute runbook scripts")
            self.assertIn(str(mutating), preview_text)
            self.assertIn("bash", preview_text)
            self.assertIn("explicit confirmation", preview_text.lower())
            self.assertIn("clone-safe", preview_text.lower())
            self.assertNotEqual(getattr(preview, "action", None), RunbookAction.RUN)
            self.assertEqual(getattr(preview, "scope", RunbookExecutionScope.CLONE_SAFE), RunbookExecutionScope.CLONE_SAFE)

    def test_runbook_default_actions_exclude_mutating_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, _mutating = self.make_runbook_root(Path(tmp))
            model = self.make_runbook_model(root)
            call_first(model, ("open_runbook", "select_runbook", "show_runbook", "runbook_detail"), "local.99-mutating-fixture")

            actions = call_first(model, ("available_actions", "actions", "selected_actions"))
            action_text = text_of(actions).lower()

            self.assertIn("validate", action_text)
            self.assertIn("preview", action_text)
            self.assertNotIn("default: run", action_text)
            self.assertNotIn("run by default", action_text)
            self.assertNotIn("environment-dependent", action_text.split("preview", 1)[0])


if __name__ == "__main__":
    unittest.main()
