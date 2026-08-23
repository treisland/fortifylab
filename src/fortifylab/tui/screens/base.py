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


@dataclass
class Armable:
    """Shared one-shot arm-to-execute state.

    Three screens now need the same dry-run-unless-armed posture
    (``GuidedDeployScreen``, ``ApplicationsScreen``, ``ConfigurationScreen``):
    dry-run is the default and stays repeatable; a real execution requires
    explicitly arming first ("a"), and arming auto-clears after one real
    execution -- arming is a per-action decision, not a per-session one.
    Without that auto-clear, a stray extra keypress (key repeat, a fumbled
    double-press) while still armed would silently run a second real
    operation instead of falling back to preview mode.
    """

    armed: bool = False

    def toggle_armed(self) -> None:
        self.armed = not self.armed

    def consume_arm(self) -> bool:
        """Report whether to execute for real right now, disarming if so.

        Call this once per action attempt in place of reading ``armed``
        directly: it hands back the current arm state and, if it was armed,
        clears it in the same step so the caller can't forget to disarm.
        """
        executing = self.armed
        if executing:
            self.armed = False
        return executing

    def mode_label(self, *, armed_text: str = "EXECUTE (armed)", dry_run_text: str = "dry-run (preview only)") -> str:
        return armed_text if self.armed else dry_run_text


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
