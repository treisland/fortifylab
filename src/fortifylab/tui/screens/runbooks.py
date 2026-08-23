"""Runbooks screen -- the interactive replacement for ``runbooks_menu()`` in
``scripts/wizard/runbooks.sh``, for the topics ``OperationCatalog.runbook()``
already knows how to preview safely (a read-only ``sed`` excerpt of the
matching doc, never the full runbook executor).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fortifylab.operations import OperationCatalog, OperationExecution, OperationRunner

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen

_TOPICS: tuple[tuple[str, str], ...] = (
    ("first-scan", "First scan"),
    ("backup", "Backup and recovery"),
    ("troubleshooting", "Troubleshooting"),
)


@dataclass
class RunbooksScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    catalog: OperationCatalog = field(default_factory=OperationCatalog)
    runner: OperationRunner = field(default_factory=OperationRunner)
    topics: tuple[tuple[str, str], ...] = _TOPICS
    selected_index: int = 0
    viewing: bool = False
    last_execution: OperationExecution | None = None

    def render(self) -> str:
        if self.viewing:
            return self._render_preview()
        return self._render_list()

    def _render_list(self) -> str:
        lines = [self.style.heading("Runbook Library"), "", "Safe, read-only previews:"]
        for index, (_topic_id, label) in enumerate(self.topics):
            marker = self.style.paint(">", "1;36") if index == self.selected_index else " "
            lines.append(f" {marker} {label}")
        lines.extend(("", self.style.muted("up/down to move, enter to preview, q: back")))
        return "\n".join(lines) + "\n"

    def _render_preview(self) -> str:
        _topic_id, label = self.topics[self.selected_index]
        lines = [self.style.heading(f"Runbook -- {label}"), ""]
        if self.last_execution is not None:
            lines.append(self.last_execution.detail)
        lines.extend(("", self.style.muted("b: back to topics, q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if self.viewing:
            if event.key in ("b", "B"):
                self.viewing = False
            return NavigationCommand.stay()
        if event.key in ("up", "k"):
            self.selected_index = (self.selected_index - 1) % len(self.topics)
        elif event.key in ("down", "j"):
            self.selected_index = (self.selected_index + 1) % len(self.topics)
        elif event.key == "enter":
            self._preview_selected()
        return NavigationCommand.stay()

    def _preview_selected(self) -> None:
        topic_id, _label = self.topics[self.selected_index]
        # Runbook previews are read-only (OperationImpact.READ_ONLY), so
        # OperationRunner never dry-run gates this -- nothing to arm.
        self.last_execution = self.runner.run(self.catalog.runbook(topic_id))
        self.viewing = True
