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
    ERASE_LINE_TO_END = "\x1b[K"

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self._started = False

    def render(self, frame: str) -> None:
        if not self._started:
            self.stream.write(self.HIDE_CURSOR)
            self._started = True
        self.stream.write(self.CURSOR_HOME)
        # Erase each line to end-of-line as it's written, not just
        # end-of-screen after the whole frame: erasing only from the final
        # cursor position leaves stale characters to the right of any row
        # that got shorter than the previous frame's same row (e.g. a menu
        # label that was previously longer), since the cursor has already
        # moved past that row by the time a single end-of-screen erase runs.
        for line in frame.splitlines():
            self.stream.write(line)
            self.stream.write(self.ERASE_LINE_TO_END)
            self.stream.write("\n")
        self.stream.write(self.ERASE_TO_END)
        self.stream.flush()

    def close(self) -> None:
        if self._started:
            self.stream.write(self.SHOW_CURSOR)
            self.stream.flush()
            self._started = False
