"""Help Center and Runbook Library workflow screens for the Python TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import shorten

from fortifylab.help import HelpRegistry, HelpTopicRecord
from fortifylab.paths import repo_root
from fortifylab.runbooks import RunbookAction, RunbookExecutionScope, RunbookMetadata, discover_runbooks, preview_runbook, script_preview
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


MAX_DETAIL_LINES = 34


@dataclass(frozen=True)
class TuiRunbookPreview:
    action: RunbookAction
    scope: RunbookExecutionScope
    command_text: str
    warnings: tuple[str, ...]

    def render(self) -> str:
        lines = [
            f"Action: {self.action.value}",
            f"Scope: {self.scope.value}",
            f"Command: {self.command_text}",
        ]
        if self.warnings:
            lines.append("Warnings: " + "; ".join(self.warnings))
        return "\n".join(lines)


@dataclass
class HelpCenterScreen(WorkflowScreen):
    def __init__(self, help_root: Path | str | None = None) -> None:
        registry = HelpRegistry.from_directory(Path(help_root) if help_root is not None else None)
        self._topics = tuple(registry.lookup(topic.id) for topic in _catalog_topics())
        self._by_id = {topic.id: topic for topic in self._topics}
        super().__init__(
            "help_center",
            "Help Center",
            "Help topic browser workflow boundary: live offline topic list and detail viewer.",
        )
        self._selected = 0
        self._detail: HelpTopicRecord | None = None

    def list_topics(self) -> tuple[HelpTopicRecord, ...]:
        return self._topics

    def topics(self) -> tuple[HelpTopicRecord, ...]:
        return self.list_topics()

    def open_topic(self, topic_id: str) -> str:
        try:
            topic = self._by_id[topic_id]
        except KeyError as exc:
            raise KeyError(topic_id) from exc
        self._selected = self._topics.index(topic)
        self._detail = topic
        return self.render()

    select_topic = open_topic
    show_topic = open_topic
    topic_detail = open_topic

    def back(self) -> str:
        self._detail = None
        return self.render()

    go_back = back
    return_to_listing = back

    @property
    def current_screen(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    @property
    def listing(self) -> str:
        return self._render_list()

    @property
    def selected_topic(self) -> HelpTopicRecord | None:
        return self._detail

    def render(self) -> str:
        if self._detail is not None:
            return self._render_detail(self._detail)
        return self._render_list()

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if self._detail is not None:
            if key in {"back", "b", "escape", "r", ""}:
                self._detail = None
                return WorkflowKeyResult("Returned to Help Center topics.")
            return WorkflowKeyResult("Use Back to return to the topic list, or q to quit.")

        if key == "up":
            self._selected = max(0, self._selected - 1)
            return WorkflowKeyResult(f"Selected {self._topics[self._selected].title}.")
        if key == "down":
            self._selected = min(len(self._topics) - 1, self._selected + 1)
            return WorkflowKeyResult(f"Selected {self._topics[self._selected].title}.")
        if key == "enter":
            self._detail = self._topics[self._selected]
            return WorkflowKeyResult(f"Opened {self._detail.title}.")
        if key.isdigit():
            index = int(key) - 1
            if 0 <= index < len(self._topics):
                self._selected = index
                self._detail = self._topics[index]
                return WorkflowKeyResult(f"Opened {self._detail.title}.")
        if key in {"back", "b", "escape", "r", ""}:
            return WorkflowKeyResult("Returned to menu.", exit_screen=True)
        return WorkflowKeyResult(f"No help topic is bound to {key!r}.")

    def _render_list(self) -> str:
        lines = [self.summary, "", "Topics:"]
        for index, topic in enumerate(self._topics, start=1):
            marker = ">" if index - 1 == self._selected else " "
            lines.append(f"{marker} {index:>2}  {topic.title}")
        lines.extend(("", "Enter opens the selected topic. Back returns to the menu."))
        return "\n".join(lines)

    def _render_detail(self, topic: HelpTopicRecord) -> str:
        relative_path = topic.offline_path.relative_to(repo_root())
        lines = [
            self.summary,
            "",
            topic.title,
            f"Topic: {topic.id}",
            f"Offline help: {relative_path}",
            "",
            *_bounded_lines(_offline_help_body(topic.body)),
            "",
            "Back returns to the topic list.",
        ]
        return "\n".join(lines)


@dataclass
class RunbookLibraryScreen(WorkflowScreen):
    def __init__(self, runbook_root: Path | str | None = None) -> None:
        super().__init__(
            "runbook_library",
            "Runbook Library",
            "Runbook browser workflow boundary: live clone-safe runbook list, detail, command preview, and script preview.",
        )
        self._runbooks = discover_runbooks(Path(runbook_root) if runbook_root is not None else None)
        self._by_id = {runbook.id: runbook for runbook in self._runbooks}
        self._selected = 0
        self._detail: RunbookMetadata | None = None

    def list_runbooks(self) -> str:
        return self._render_list()

    def runbooks(self) -> str:
        return self.list_runbooks()

    runbook_listing = list_runbooks

    def open_runbook(self, runbook_id: str) -> str:
        try:
            runbook = self._by_id[runbook_id]
        except KeyError as exc:
            raise KeyError(runbook_id) from exc
        self._selected = self._runbooks.index(runbook)
        self._detail = runbook
        return self.render()

    select_runbook = open_runbook
    show_runbook = open_runbook
    runbook_detail = open_runbook

    def preview_runbook(self) -> TuiRunbookPreview:
        selected = self._selected_runbook()
        preview = preview_runbook(selected)
        return TuiRunbookPreview(preview.action, preview.scope, preview.command_text, preview.warnings)

    preview = preview_runbook
    preview_selected = preview_runbook
    preview_command = preview_runbook

    def available_actions(self) -> tuple[str, ...]:
        selected = self._selected_runbook()
        actions = [f"{action.value} ({RunbookExecutionScope.CLONE_SAFE.value})" for action in selected.clone_safe_actions]
        actions.append(f"run ({RunbookExecutionScope.ENVIRONMENT_DEPENDENT.value}, explicit confirmation required)")
        return tuple(actions)

    actions = available_actions
    selected_actions = available_actions

    def back(self) -> str:
        self._detail = None
        return self.render()

    go_back = back
    return_to_listing = back

    @property
    def current_screen(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    @property
    def listing(self) -> str:
        return self._render_list()

    @property
    def selected_runbook(self) -> RunbookMetadata | None:
        return self._detail

    def render(self) -> str:
        if self._detail is not None:
            return self._render_detail(self._detail)
        return self._render_list()

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if not self._runbooks:
            if key in {"back", "b", "escape", "r", ""}:
                return WorkflowKeyResult("Returned to menu.", exit_screen=True)
            return WorkflowKeyResult("No runbooks are available.")

        if self._detail is not None:
            if key in {"back", "b", "escape", "r", ""}:
                self._detail = None
                return WorkflowKeyResult("Returned to Runbook Library.")
            return WorkflowKeyResult("Runbook execution is preview-only in the TUI; use Back to return.")

        if key == "up":
            self._selected = max(0, self._selected - 1)
            return WorkflowKeyResult(f"Selected {self._runbooks[self._selected].name}.")
        if key == "down":
            self._selected = min(len(self._runbooks) - 1, self._selected + 1)
            return WorkflowKeyResult(f"Selected {self._runbooks[self._selected].name}.")
        if key == "enter":
            self._detail = self._runbooks[self._selected]
            return WorkflowKeyResult(f"Opened {self._detail.name}.")
        if key.isdigit():
            index = int(key) - 1
            if 0 <= index < len(self._runbooks):
                self._selected = index
                self._detail = self._runbooks[index]
                return WorkflowKeyResult(f"Opened {self._detail.name}.")
        if key in {"back", "b", "escape", "r", ""}:
            return WorkflowKeyResult("Returned to menu.", exit_screen=True)
        return WorkflowKeyResult(f"No runbook is bound to {key!r}.")

    def _render_list(self) -> str:
        lines = [self.summary, "", "Runbooks:"]
        current_domain = None
        for index, runbook in enumerate(self._runbooks, start=1):
            if runbook.domain != current_domain:
                current_domain = runbook.domain
                lines.append(f"{current_domain}:")
            marker = ">" if index - 1 == self._selected else " "
            risk = runbook.risk.value
            description = shorten(runbook.description, width=62, placeholder="...")
            lines.append(f"{marker} {index:>2}  {runbook.name} [{runbook.source.value}, {risk}]")
            lines.append(f"      {description}")
        if not self._runbooks:
            lines.append("No FortifyLab runbooks were discovered.")
        lines.extend(("", "Enter opens metadata and clone-safe previews. Back returns to the menu."))
        return "\n".join(lines)

    def _render_detail(self, runbook: RunbookMetadata) -> str:
        command = preview_runbook(runbook)
        script = script_preview(runbook, max_lines=18)
        relative_path = _display_path(runbook.path)
        lines = [
            self.summary,
            "",
            runbook.name,
            f"ID: {runbook.id}",
            f"Source: {runbook.source.value}",
            f"Domain: {runbook.domain}",
            f"Category: {runbook.category}",
            f"Risk: {runbook.risk.value}",
            f"Path: {relative_path}",
            f"Description: {runbook.description}",
            "",
            "Requirements: " + (", ".join(runbook.requires) if runbook.requires else "none declared"),
            "Parameters: " + _parameter_summary(runbook),
            "",
            "Clone-safe command preview:",
            command.command_text or "(no command preview)",
        ]
        if command.warnings:
            lines.append("Warnings: " + "; ".join(command.warnings))
        lines.extend(
            (
                "",
                "Script preview:",
                *_bounded_lines(script.script_excerpt, limit=18),
                "",
                "Execution is not performed here. Run actions remain environment-dependent and confirmation-gated.",
                "Back returns to the runbook list.",
            )
        )
        return "\n".join(lines)

    def _selected_runbook(self) -> RunbookMetadata:
        if self._detail is not None:
            return self._detail
        if not self._runbooks:
            raise LookupError("No runbooks are available.")
        return self._runbooks[self._selected]


def _catalog_topics():
    from fortifylab.runbooks import list_help_topics

    return list_help_topics()


def _display_path(path: Path) -> Path | str:
    try:
        return path.relative_to(repo_root())
    except ValueError:
        return str(path)


def _offline_help_body(text: str) -> str:
    return text.replace("https://", "").replace("http://", "")


def _bounded_lines(text: str, *, limit: int = MAX_DETAIL_LINES) -> tuple[str, ...]:
    lines = tuple(text.strip().splitlines())
    if len(lines) <= limit:
        return lines
    remaining = len(lines) - limit
    return (*lines[:limit], f"... {remaining} more lines not shown ...")


def _parameter_summary(runbook: RunbookMetadata) -> str:
    if not runbook.parameters:
        return "none declared"
    parts = []
    for parameter in runbook.parameters:
        required = "required" if parameter.required else "optional"
        default = "env" if parameter.default_from_env else ("default" if parameter.default else "no default")
        parts.append(f"{parameter.name} ({required}, {default})")
    return "; ".join(parts)
