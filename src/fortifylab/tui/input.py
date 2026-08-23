"""Raw-mode terminal input, turned into :mod:`fortifylab.tui.events`.

This is the one module allowed to know about file descriptors, termios, and
escape sequences. Everything above it (router, screens) only ever sees
:class:`~fortifylab.tui.events.KeyEvent`.
"""

from __future__ import annotations

import os
import select
import sys
from types import TracebackType
from typing import TextIO

from .events import Event, KeyEvent

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - posix-only terminal handling
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

_ESCAPE_SEQUENCES = {
    "\x1b[A": "up",
    "\x1b[B": "down",
    "\x1b[C": "right",
    "\x1b[D": "left",
}


def _normalize_key(raw: str) -> str:
    if raw in ("\r", "\n"):
        return "enter"
    if raw == "\x1b":
        return "escape"
    if raw == "\x03":
        return "ctrl-c"
    return raw


class TerminalInput:
    """Reads raw keypresses from a stream and yields normalized
    :class:`KeyEvent` objects, entering cbreak mode for the duration of the
    ``with`` block so Ctrl-C still raises ``KeyboardInterrupt`` instead of
    being swallowed as a literal byte."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdin
        self._fd = self.stream.fileno()
        self._original_settings: object | None = None

    def __enter__(self) -> "TerminalInput":
        if termios is None or not self.stream.isatty():
            raise RuntimeError(
                "The interactive TUI requires a real terminal (a TTY) for input. "
                "Run it from an interactive shell, not a pipe or non-interactive script."
            )
        self._original_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._original_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_settings)
            self._original_settings = None

    def read_event(self, *, timeout: float | None = None) -> Event | None:
        """Return the next input event, or ``None`` if ``timeout`` elapses
        first (so a caller can interleave :class:`~fortifylab.tui.events.TickEvent`
        without blocking forever on a keypress).

        Reads the raw file descriptor directly rather than through
        ``self.stream``: a buffered ``TextIOWrapper`` both applies universal
        newline translation (which blocks waiting for possible "\\r\\n"
        lookahead on a lone "\\r") and reads ahead into its own internal
        buffer, which silently desyncs it from ``select()`` polling the fd.
        """

        first = self._read_byte(timeout=timeout)
        if first is None:
            return None
        if first == "\x1b":
            sequence = first + self._read_escape_tail()
            return KeyEvent(_ESCAPE_SEQUENCES.get(sequence, "escape"))
        return KeyEvent(_normalize_key(first))

    def _read_byte(self, *, timeout: float | None) -> str | None:
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return None
        return os.read(self._fd, 1).decode(errors="replace")

    def _read_escape_tail(self) -> str:
        chunk = self._read_byte(timeout=0.05)
        if chunk is None:
            return ""
        if chunk != "[":
            return chunk
        final = self._read_byte(timeout=0.05)
        if final is None:
            return chunk
        return chunk + final
