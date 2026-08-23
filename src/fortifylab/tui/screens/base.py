"""The screen abstraction that replaces Bash's nested
``while true; case $choice`` menu loops (``scripts/wizard/menu.sh``) with
one small class per menu.

A screen never touches the router, a terminal fd, or `subprocess` directly:
it renders a string and reacts to events, and hands back a
``NavigationCommand`` describing *what* should happen (push/pop/quit), never
*how*. That keeps every screen unit-testable with plain events and no fake
terminal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from ..events import Event


class NavigationKind(str, Enum):
    STAY = "stay"
    PUSH = "push"
    POP = "pop"
    REPLACE = "replace"
    QUIT = "quit"


@dataclass(frozen=True)
class NavigationCommand:
    kind: NavigationKind
    screen: "Screen | None" = None

    @classmethod
    def stay(cls) -> "NavigationCommand":
        return cls(NavigationKind.STAY)

    @classmethod
    def push(cls, screen: "Screen") -> "NavigationCommand":
        return cls(NavigationKind.PUSH, screen)

    @classmethod
    def pop(cls) -> "NavigationCommand":
        return cls(NavigationKind.POP)

    @classmethod
    def replace(cls, screen: "Screen") -> "NavigationCommand":
        return cls(NavigationKind.REPLACE, screen)

    @classmethod
    def quit(cls) -> "NavigationCommand":
        return cls(NavigationKind.QUIT)


class Screen(ABC):
    """One menu or workspace. ``render()`` must be pure (no I/O) so a test
    can call it directly and assert on the returned string."""

    @abstractmethod
    def render(self) -> str: ...

    @abstractmethod
    def handle_event(self, event: Event) -> NavigationCommand: ...

    def on_enter(self) -> None:
        """Called once when the router pushes this screen. Override to
        refresh live data; default does nothing."""

    def on_exit(self) -> None:
        """Called once when the router pops this screen. Default does
        nothing."""
