"""Typed navigation contracts for FortifyLab's Python TUI migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Literal


class ActionKind(str, Enum):
    """Kinds of actions a menu item can target before operations are wired."""

    MENU = "menu"
    WORKFLOW = "workflow"
    VIEW = "view"
    COMMAND = "command"
    QUIT = "quit"
    RETURN = "return"
    PLACEHOLDER = "placeholder"


NavigationKeyMode = Literal["jump_highlight", "activate"]


@dataclass(frozen=True)
class ActionRef:
    """Stable reference to a future screen, workflow, command, or adapter."""

    kind: ActionKind
    target: str
    placeholder: bool = True


@dataclass(frozen=True)
class MenuItem:
    """A selectable item in a menu screen."""

    key: str
    label: str
    action: ActionRef
    aliases: tuple[str, ...] = ()
    disabled_reason: str | None = None
    description: str | None = None

    @property
    def enabled(self) -> bool:
        return self.disabled_reason is None

    def matches(self, value: str) -> bool:
        return value == self.key or value in self.aliases


@dataclass(frozen=True)
class MenuNode:
    """A deterministic menu screen model consumable by tests and TUI code."""

    id: str
    title: str
    items: tuple[MenuItem, ...]
    back_aliases: tuple[str, ...] = ("b", "escape")
    return_aliases: tuple[str, ...] = ()
    quit_aliases: tuple[str, ...] = ("q",)
    number_key_mode: NavigationKeyMode = "jump_highlight"
    workflow_boundary: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.items)

    def labels(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.items)

    def enabled_items(self) -> tuple[MenuItem, ...]:
        return tuple(item for item in self.items if item.enabled)

    def item_for_key(self, key: str) -> MenuItem | None:
        for item in self.items:
            if item.matches(key):
                return item
        return None

    def disabled_items(self) -> tuple[MenuItem, ...]:
        return tuple(item for item in self.items if not item.enabled)


def item(
    key: str,
    label: str,
    kind: ActionKind,
    target: str,
    *,
    aliases: Iterable[str] = (),
    disabled_reason: str | None = None,
    description: str | None = None,
    placeholder: bool = True,
) -> MenuItem:
    """Create a menu item with tuple-normalized aliases."""

    return MenuItem(
        key=key,
        label=label,
        action=ActionRef(kind=kind, target=target, placeholder=placeholder),
        aliases=tuple(aliases),
        disabled_reason=disabled_reason,
        description=description,
    )
