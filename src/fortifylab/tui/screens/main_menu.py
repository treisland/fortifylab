"""Main menu screen — the interactive replacement for ``main_menu()`` in
``scripts/wizard/menu.sh``.

Scope for this milestone (M2): navigation and preview only. Selecting an
item shows its description, matching what ``./bin/fortifylab deploy --plan``
already does for a mutating operation today — a readable preview, not a
live run. Wiring real execution behind these entries is M3+.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..events import Event, KeyEvent
from ..menu import OPERATOR_MENU, MenuItem
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen

_UP_KEYS = {"up", "k"}
_DOWN_KEYS = {"down", "j"}
_QUIT_KEYS = {"q", "Q"}


@dataclass
class MainMenuScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    items: tuple[MenuItem, ...] = OPERATOR_MENU
    selected_index: int = 0
    show_detail: bool = False

    def render(self) -> str:
        lines = [self.style.heading("Fortify Lab Operator Console"), "", "Task workspaces:"]
        for index, item in enumerate(self.items):
            marker = self.style.paint(">", "1;36") if index == self.selected_index else " "
            lines.append(f" {marker} {index + 1:2d}. {item.label:<22} {self.style.muted(item.description)}")
        if self.show_detail:
            selected = self.items[self.selected_index]
            lines.extend(
                (
                    "",
                    self.style.heading(f"Preview: {selected.label}"),
                    f"  {selected.description}",
                    self.style.muted("  (preview only -- no action has been taken)"),
                )
            )
        lines.extend(
            (
                "",
                self.style.muted("up/down or j/k to move, enter to preview, ? for help, q to quit."),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in _QUIT_KEYS:
            return NavigationCommand.quit()
        if event.key in _UP_KEYS:
            self.selected_index = (self.selected_index - 1) % len(self.items)
            self.show_detail = False
            return NavigationCommand.stay()
        if event.key in _DOWN_KEYS:
            self.selected_index = (self.selected_index + 1) % len(self.items)
            self.show_detail = False
            return NavigationCommand.stay()
        if event.key == "enter":
            self.show_detail = not self.show_detail
            return NavigationCommand.stay()
        if event.key == "?":
            self._select_by_key("help")
            self.show_detail = True
            return NavigationCommand.stay()
        if event.key.isdigit():
            self._select_by_position(int(event.key))
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _select_by_position(self, one_based: int) -> None:
        index = one_based - 1
        if 0 <= index < len(self.items):
            self.selected_index = index
            self.show_detail = True

    def _select_by_key(self, key: str) -> None:
        for index, item in enumerate(self.items):
            if item.key == key:
                self.selected_index = index
                return
