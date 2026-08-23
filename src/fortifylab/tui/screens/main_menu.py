"""Main menu screen — the interactive replacement for ``main_menu()`` in
``scripts/wizard/menu.sh``.

Most items are still navigation and preview only (M2 scope): selecting one
shows its description, matching what ``./bin/fortifylab deploy --plan``
already does for a mutating operation today — a readable preview, not a
live run. An item gets a real screen (opened with "o") only once one has
actually been built for it -- see ``_SCREEN_FACTORIES`` below; "deploy" is
the first (M3).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..events import Event, KeyEvent
from ..menu import OPERATOR_MENU, MenuItem
from ..theme import TerminalStyle
from .applications import ApplicationsScreen
from .base import NavigationCommand, Screen
from .configuration import ConfigurationScreen
from .diagnostics import DiagnosticsScreen
from .guided_deploy import GuidedDeployScreen
from .help import HelpScreen
from .logs import LogsScreen
from .runbooks import RunbooksScreen

_UP_KEYS = {"up", "k"}
_DOWN_KEYS = {"down", "j"}
_QUIT_KEYS = {"q", "Q"}

# Menu item key -> factory for its real screen. An item not listed here is
# still preview-only; add its factory here once its screen exists (M6).
_SCREEN_FACTORIES: dict[str, Callable[[], Screen]] = {
    "deploy": GuidedDeployScreen,
    "applications": ApplicationsScreen,
    "configuration": ConfigurationScreen,
    "logs": LogsScreen,
    "diagnostics": DiagnosticsScreen,
    "runbooks": RunbooksScreen,
    "help": HelpScreen,
}


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
                )
            )
            if selected.key in _SCREEN_FACTORIES:
                lines.append(self.style.muted("  press o to open"))
            else:
                lines.append(self.style.muted("  (preview only -- no action has been taken)"))
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
        if event.key in ("o", "O"):
            factory = _SCREEN_FACTORIES.get(self.items[self.selected_index].key)
            if factory is not None:
                return NavigationCommand.push(factory())
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _select_by_position(self, one_based: int) -> None:
        # Conventional terminal-menu digit mapping: 1-9 select items 1-9, and
        # "0" selects the 10th item (there is no digit for one-based position
        # 10 otherwise, so a bare "0" would silently fail to select anything).
        index = 9 if one_based == 0 else one_based - 1
        if 0 <= index < len(self.items):
            self.selected_index = index
            self.show_detail = True

    def _select_by_key(self, key: str) -> None:
        for index, item in enumerate(self.items):
            if item.key == key:
                self.selected_index = index
                return
