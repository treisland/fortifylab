"""Pure key handling for FortifyLab navigation menus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import ActionKind, MenuItem, MenuNode


ResultKind = Literal["activate", "back", "disabled", "help", "noop", "quit", "select"]


KEY_ALIASES = {
    "?": "help",
    "ctrl+c": "quit",
    "ctrl_q": "quit",
    "ctrl+q": "quit",
    "esc": "back",
    "escape": "back",
    "h": "help",
    "help": "help",
    "j": "down",
    "k": "up",
    "q": "quit",
    "return": "enter",
    "space": "enter",
}


@dataclass(frozen=True)
class MenuResult:
    """Result returned from a deterministic menu key event."""

    kind: ResultKind
    raw_key: str
    normalized_key: str
    selected_item: MenuItem | None = None
    activated_item: MenuItem | None = None
    disabled_reason: str | None = None
    action_kind: ActionKind | None = None
    action_target: str | None = None


def normalize_menu_key(raw_key: str) -> str:
    """Normalize terminal/Textual key names into FortifyLab menu commands."""

    key = raw_key.strip().lower()
    if key in ("", "\n", "\r"):
        return "enter"
    if key in ("enter", "return"):
        return "enter"
    if key in ("up", "cursor_up"):
        return "up"
    if key in ("down", "cursor_down"):
        return "down"
    if key in ("b", "r"):
        return "back"
    return KEY_ALIASES.get(key, key)


class MenuController:
    """Stateful selection controller for one menu node.

    The controller has no terminal dependency. Textual screens and tests can
    drive it with symbolic key names such as ``down``, ``3``, and ``enter``.
    """

    def __init__(self, menu: MenuNode, *, selected_key: str | None = None) -> None:
        if not menu.items:
            raise ValueError(f"menu {menu.id!r} has no items")
        self.menu = menu
        self.selected_index = self._index_for_key(selected_key) if selected_key else 0

    @property
    def selected_item(self) -> MenuItem:
        return self.menu.items[self.selected_index]

    def handle_key(self, raw_key: str) -> MenuResult:
        """Handle a normalized or raw key without activating on number jumps."""

        if raw_key == "" and ("" in self.menu.return_aliases or "" in self.menu.back_aliases):
            return self._back_result(raw_key, "")

        normalized = normalize_menu_key(raw_key)

        if normalized == "up":
            return self._move(raw_key, normalized, -1)
        if normalized == "down":
            return self._move(raw_key, normalized, 1)
        if normalized == "enter":
            return self._activate(raw_key, normalized, self.selected_item)
        if normalized == "help":
            return MenuResult("help", raw_key, normalized, selected_item=self.selected_item)
        if normalized == "quit" or normalized in self.menu.quit_aliases:
            return MenuResult("quit", raw_key, normalized, selected_item=self.selected_item)
        if normalized == "back" or normalized in self.menu.back_aliases or normalized in self.menu.return_aliases:
            return self._back_result(raw_key, normalized)

        matched = self.menu.item_for_key(normalized)
        if matched is not None:
            self.selected_index = self._index_for_item(matched)
            if self.menu.number_key_mode == "activate":
                return self._activate(raw_key, normalized, matched)
            return MenuResult("select", raw_key, normalized, selected_item=matched)

        return MenuResult("noop", raw_key, normalized, selected_item=self.selected_item)

    def _move(self, raw_key: str, normalized: str, delta: int) -> MenuResult:
        self.selected_index = (self.selected_index + delta) % len(self.menu.items)
        return MenuResult("select", raw_key, normalized, selected_item=self.selected_item)

    def _activate(self, raw_key: str, normalized: str, selected: MenuItem) -> MenuResult:
        if selected.disabled_reason is not None:
            return MenuResult(
                "disabled",
                raw_key,
                normalized,
                selected_item=selected,
                disabled_reason=selected.disabled_reason,
                action_kind=selected.action.kind,
                action_target=selected.action.target,
            )
        if selected.action.kind == ActionKind.QUIT:
            return MenuResult(
                "quit",
                raw_key,
                normalized,
                selected_item=selected,
                activated_item=selected,
                action_kind=selected.action.kind,
                action_target=selected.action.target,
            )
        if selected.action.kind == ActionKind.RETURN:
            return MenuResult(
                "back",
                raw_key,
                normalized,
                selected_item=selected,
                activated_item=selected,
                action_kind=selected.action.kind,
                action_target=selected.action.target,
            )
        return MenuResult(
            "activate",
            raw_key,
            normalized,
            selected_item=selected,
            activated_item=selected,
            action_kind=selected.action.kind,
            action_target=selected.action.target,
        )

    def _back_result(self, raw_key: str, normalized: str) -> MenuResult:
        back_item = self._first_return_item()
        if back_item is not None:
            self.selected_index = self._index_for_item(back_item)
        return MenuResult(
            "back",
            raw_key,
            normalized,
            selected_item=self.selected_item,
            activated_item=back_item,
            action_kind=back_item.action.kind if back_item else ActionKind.RETURN,
            action_target=back_item.action.target if back_item else "",
        )

    def _first_return_item(self) -> MenuItem | None:
        for menu_item in self.menu.items:
            if menu_item.action.kind == ActionKind.RETURN:
                return menu_item
        return None

    def _index_for_key(self, selected_key: str | None) -> int:
        if selected_key is None:
            return 0
        item = self.menu.item_for_key(selected_key)
        if item is None:
            raise ValueError(f"menu {self.menu.id!r} has no item for key {selected_key!r}")
        return self._index_for_item(item)

    def _index_for_item(self, selected: MenuItem) -> int:
        for index, menu_item in enumerate(self.menu.items):
            if menu_item is selected or menu_item == selected:
                return index
        raise ValueError(f"item {selected.key!r} is not in menu {self.menu.id!r}")
