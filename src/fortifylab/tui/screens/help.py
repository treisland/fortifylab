"""Help Center screen -- the interactive replacement for ``help_center()``
in ``scripts/lib/help.sh``.

Offline and read-only: viewing a topic never queries or changes Kubernetes,
files, or credentials, same guarantee the Bash Help Center's own banner
makes. Renders the same committed ``docs/help/*.txt`` files the Bash
version reads, through ``fortifylab.domain.help_center``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fortifylab.domain.help_center import HELP_TOPICS, HelpTopic, load_topic_text

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


@dataclass
class HelpScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    topics: tuple[HelpTopic, ...] = HELP_TOPICS
    selected_index: int = 0
    viewing: bool = False
    content: str | None = None
    error: str | None = None

    def render(self) -> str:
        if self.viewing:
            return self._render_topic()
        return self._render_list()

    def _render_list(self) -> str:
        lines = [
            self.style.heading("Help Center"),
            "",
            "Offline, read-only guidance for understanding this Fortify lab.",
            "Viewing a help topic never queries or changes Kubernetes, files, or credentials.",
            "",
        ]
        for index, topic in enumerate(self.topics):
            marker = self.style.paint(">", "1;36") if index == self.selected_index else " "
            lines.append(f" {marker} {index + 1:2d}. {topic.label}")
        lines.extend(("", self.style.muted("up/down to move, enter to view, q: back")))
        return "\n".join(lines) + "\n"

    def _render_topic(self) -> str:
        topic = self.topics[self.selected_index]
        lines = [self.style.heading(f"Help -- {topic.label}"), ""]
        if self.error is not None:
            lines.append(self.style.fail(self.error))
        else:
            lines.append(self.content or "")
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
            self._view_selected()
        return NavigationCommand.stay()

    def _view_selected(self) -> None:
        topic = self.topics[self.selected_index]
        try:
            self.content = load_topic_text(topic)
            self.error = None
        except FileNotFoundError:
            self.content = None
            self.error = f"Help document is unavailable: docs/help/{topic.filename}"
        self.viewing = True
