"""Terminal style helpers for CLI/TUI previews."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class TerminalStyle:
    """Small ANSI style layer with NO_COLOR and plain-mode support."""

    color: bool = True
    symbols: bool = True

    @classmethod
    def from_environment(cls, *, plain: bool = False) -> "TerminalStyle":
        color = not plain and "NO_COLOR" not in os.environ
        return cls(color=color, symbols=not plain)

    def paint(self, text: str, code: str) -> str:
        if not self.color:
            return text
        return f"[{code}m{text}[0m"

    def heading(self, text: str) -> str:
        return self.paint(text, "1;34")

    def ok(self, text: str) -> str:
        return self.paint(text, "32")

    def warn(self, text: str) -> str:
        return self.paint(text, "33")

    def running(self, text: str) -> str:
        return self.paint(text, "36")

    def fail(self, text: str) -> str:
        return self.paint(text, "31")

    def muted(self, text: str) -> str:
        return self.paint(text, "2")

    def symbol(self, name: str) -> str:
        if not self.symbols:
            return {"ok": "OK", "warn": "WARN", "fail": "FAIL", "next": "NEXT", "running": "RUN"}.get(name, "-")
        return {"ok": "✓", "warn": "!", "fail": "✕", "next": "→", "running": "●"}.get(name, "-")
