"""Configuration screen -- the interactive replacement for ``edit_env()`` in
``scripts/wizard/menu.sh``, for the parts the Python config engine
(``fortifylab.config``) already covers: a redacted view of the current
``.env``, and backup/rollback.

Editing an individual value interactively is not wired here: that needs
free-text entry (a key name and a new value), and there is no text-entry
widget in the TUI yet. `./bin/fortifylab config diff KEY=value` already
covers scripted edits; this screen covers the parts that don't need typing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fortifylab.config.envfile import display_value
from fortifylab.config.store import ConfigStore

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


@dataclass
class ConfigurationScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    store: ConfigStore = field(default_factory=lambda: ConfigStore(Path(".env")))
    armed: bool = False
    last_message: str | None = None

    def render(self) -> str:
        lines = [self.style.heading("Configuration"), "", f"File: {self.store.env_file}", ""]
        try:
            document = self.store.load()
        except FileNotFoundError:
            lines.append(self.style.fail(f"{self.store.env_file} does not exist yet."))
            lines.extend(("", self.style.muted("q: back")))
            return "\n".join(lines) + "\n"

        values = document.values()
        for key in sorted(values):
            lines.append(f"  {key:<36} {display_value(key, values[key])}")

        backups = self.store.backups()
        lines.append("")
        lines.append(f"Backups available: {len(backups)}")
        if backups:
            lines.append(f"  most recent: {backups[0].name}")

        lines.append("")
        mode_label = "armed" if self.armed else "not armed"
        lines.append(f"Mode: {mode_label}")
        if self.last_message is not None:
            lines.append(f"Last: {self.last_message}")

        lines.extend(
            (
                "",
                self.style.muted("b: create backup   a: arm   r: rollback to last backup (requires arm)   q: back"),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("a", "A"):
            self.armed = not self.armed
            return NavigationCommand.stay()
        if event.key in ("b", "B"):
            self._create_backup()
            return NavigationCommand.stay()
        if event.key in ("r", "R"):
            self._rollback()
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _create_backup(self) -> None:
        # Backing up is additive and non-destructive -- no arming required.
        try:
            backup = self.store.prepare_backup("tui-manual-backup")
            self.last_message = f"Backup created: {backup.name}"
        except (FileNotFoundError, OSError) as exc:
            self.last_message = f"Backup failed: {exc}"

    def _rollback(self) -> None:
        if not self.armed:
            self.last_message = "Press a to arm, then r again to roll back."
            return
        try:
            backup = self.store.rollback_last()
            self.last_message = f"Rolled back from: {backup.name}"
        except FileNotFoundError as exc:
            self.last_message = f"Rollback failed: {exc}"
        finally:
            # One-shot arming, same rationale as GuidedDeployScreen/
            # ApplicationsScreen: arming is a per-action decision.
            self.armed = False
