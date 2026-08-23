"""Diagnostics screen -- the interactive replacement for ``live_status()``
in ``scripts/wizard/menu.sh``, backed by the existing
``fortifylab.diagnostics.ClusterCollector`` (already read-only and
injectable, unchanged here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from fortifylab.diagnostics import ClusterCollector, CollectorResult, write_bundle

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


def default_diagnostics_dir() -> Path:
    """Mirrors the Bash wizard's ``fortifylab_state_path diagnostics``:
    ``$XDG_STATE_HOME/fortify-lab/diagnostics``, falling back to
    ``~/.local/state/fortify-lab/diagnostics``."""

    state_root = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_root) / "fortify-lab" / "diagnostics"


@dataclass
class DiagnosticsScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    collector: ClusterCollector = field(default_factory=ClusterCollector)
    bundle_dir: Path = field(default_factory=default_diagnostics_dir)
    results: tuple[CollectorResult, ...] = ()
    message: str | None = None

    def render(self) -> str:
        lines = [self.style.heading("Diagnostics"), ""]
        if not self.results:
            lines.append(self.style.muted("No collection run yet."))
        for result in self.results:
            marker = self.style.symbol("ok") if result.ok else self.style.symbol("fail")
            lines.append(f"  {marker} {result.name}")
        if self.message is not None:
            lines.extend(("", self.message))
        lines.extend(
            (
                "",
                self.style.muted("enter/r: collect (read-only)   b: write sanitized diagnostics bundle   q: back"),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("enter", "r", "R"):
            self._collect()
            return NavigationCommand.stay()
        if event.key in ("b", "B"):
            self._write_bundle()
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _collect(self) -> None:
        # Read-only: ClusterCollector only ever runs `kubectl get`/`helm
        # list`-style commands -- no arming needed, same as LogsScreen.
        self.results = self.collector.collect()
        self.message = None

    def _write_bundle(self) -> None:
        if not self.results:
            self.message = self.style.fail("Run a collection first (enter/r) before writing a bundle.")
            return
        files = {f"{result.name}.txt": result.output for result in self.results}
        files["README.txt"] = "Fortify Lab sanitized diagnostics bundle.\n"
        bundle = write_bundle(self.bundle_dir, files)
        self.message = self.style.ok(f"Diagnostics bundle written: {bundle.path}")
