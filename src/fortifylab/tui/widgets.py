"""Small reusable input widgets, composed into a screen rather than screens
themselves -- the piece every typed-confirmation gap in the migration
(destroy, ``REVEAL``, ``PERSISTENT``, free-text ``.env`` edits) has been
waiting on.

A widget only ever touches its own field of state and reports whether it
consumed an event; it never renders a whole screen or returns a
``NavigationCommand``. That keeps the same "plain data in, plain data out"
testability every :class:`~fortifylab.tui.screens.base.Screen` already has,
and lets a screen decide for itself what Enter/Escape mean (submit and
compare against a confirmation phrase, cancel back to a menu, etc.) instead
of the widget guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .events import Event, KeyEvent


@dataclass
class TextField:
    """A single-line, append/backspace-only text buffer.

    Deliberately no cursor movement, no paste, no multi-line support --
    every use case this unblocks (typing an exact confirmation phrase, a
    replica count, a short ``.env`` value) is a short line typed left to
    right and corrected with backspace, matching what a real terminal's
    line-editing already feels like for that. Enter/Escape are NOT
    consumed here: a screen embedding this widget decides what those mean
    (submit-and-compare, cancel), so this only ever handles the keys that
    edit the buffer itself.
    """

    value: str = ""
    max_length: int = 200

    def handle_key(self, event: Event) -> bool:
        """Apply ``event`` to the buffer if it's an editing key; return
        whether it was consumed (so a caller knows not to also treat it
        as e.g. a menu navigation key)."""

        if not isinstance(event, KeyEvent):
            return False
        if event.key == "backspace":
            self.value = self.value[:-1]
            return True
        if len(event.key) == 1 and event.key.isprintable():
            if len(self.value) < self.max_length:
                self.value += event.key
            return True
        return False

    def clear(self) -> None:
        self.value = ""

    def render(self, *, cursor: str = "_") -> str:
        return f"{self.value}{cursor}"
