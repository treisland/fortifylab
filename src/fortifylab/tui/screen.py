"""Terminal screen helpers for in-place TUI refreshes."""

from __future__ import annotations

import sys
from typing import TextIO


class TerminalScreen:
    """Render frames in place to avoid visible full-screen flash."""

    HIDE_CURSOR = "\x1b[?25l"
    SHOW_CURSOR = "\x1b[?25h"
    CURSOR_HOME = "\x1b[H"
    ERASE_TO_END = "\x1b[J"

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self._started = False

    def render(self, frame: str) -> None:
        if not self._started:
            self.stream.write(self.HIDE_CURSOR)
            self._started = True
        self.stream.write(self.CURSOR_HOME)
        self.stream.write(frame)
        self.stream.write(self.ERASE_TO_END)
        self.stream.flush()

    def close(self) -> None:
        if self._started:
            self.stream.write(self.SHOW_CURSOR)
            self.stream.flush()
            self._started = False
