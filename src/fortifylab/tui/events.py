"""Input and lifecycle events for the interactive TUI event loop.

Screens only ever see one of these three types — never raw bytes, never a
terminal fd — so a screen's ``handle_event`` is testable with plain data and
has no dependency on how input actually arrives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class KeyEvent:
    """A single logical keypress. ``key`` is a normalized name for special
    keys ("up", "down", "enter", "escape", "q", ...) or the literal
    character for anything else (e.g. "1")."""

    key: str


@dataclass(frozen=True)
class TickEvent:
    """A periodic wake-up so a screen can refresh live data (dashboard
    collectors, deployment progress) without waiting on a keypress."""

    elapsed_seconds: float


@dataclass(frozen=True)
class ResizeEvent:
    columns: int
    rows: int


Event = Union[KeyEvent, TickEvent, ResizeEvent]
