"""Applications screen -- the interactive replacement for ``apps_menu()``'s
and ``sample_apps_menu()``'s start/stop actions in ``scripts/wizard/menu.sh``,
for the apps ``OperationCatalog`` already knows how to run (``ssc``,
``lim``, ``mysql``, ``postgresql``, and the sample apps ``juice-shop``,
``webgoat``, ``dvwa``).

Bash keeps core apps and sample apps on separate menu numbers, but the
underlying operation shape is identical (start/stop via a script,
`OperationCatalog.app()` already treats them the same way), so this one
screen covers both rather than duplicating the same list/arm/run logic in
a second near-identical screen -- sample apps are just labeled "(sample)".

Destroy is intentionally not wired here: every destroy operation requires
typing an exact confirmation phrase (``OperationSpec.confirmation_phrase``,
e.g. ``"DESTROY ssc"``), and there is no text-entry widget in the TUI yet.
Mapping a single keypress to "yes, destroy it" to work around that would be
exactly the kind of unsafe shortcut this codebase's confirmation-phrase
design exists to prevent, so destroy stays a Bash-wizard-only action until
the TUI has real text input (tracked in the roadmap, not invented here).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fortifylab.operations import OperationCatalog, OperationExecution, OperationRunner

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import Armable, NavigationCommand, Screen

_APPS: tuple[tuple[str, str], ...] = (
    ("ssc", "Software Security Center"),
    ("lim", "License and Infrastructure Manager"),
    ("mysql", "MySQL"),
    ("postgresql", "PostgreSQL"),
    ("juice-shop", "Juice Shop (sample)"),
    ("webgoat", "WebGoat (sample)"),
    ("dvwa", "DVWA (sample)"),
)
_ACTIONS: tuple[str, ...] = ("start", "stop")


@dataclass
class ApplicationsScreen(Armable, Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    catalog: OperationCatalog = field(default_factory=OperationCatalog)
    runner: OperationRunner = field(default_factory=OperationRunner)
    rows: tuple[tuple[str, str, str], ...] = field(
        default_factory=lambda: tuple((app_id, label, action) for app_id, label in _APPS for action in _ACTIONS)
    )
    selected_index: int = 0
    last_execution: OperationExecution | None = None

    def render(self) -> str:
        lines = [self.style.heading("Applications"), ""]
        for index, (_app_id, label, action) in enumerate(self.rows):
            marker = self.style.paint(">", "1;36") if index == self.selected_index else " "
            lines.append(f" {marker} {label:<32} {action}")
        lines.append("")
        lines.append(f"Mode: {self.mode_label()}")
        if self.last_execution is not None:
            state = "ran" if self.last_execution.executed else "previewed"
            outcome = "ok" if self.last_execution.ok else "failed"
            lines.append(f"Last: {self.last_execution.operation_id} ({state}, {outcome}) -- {self.last_execution.detail}")
        lines.extend(
            (
                "",
                self.style.muted("up/down to move, enter to run, a: toggle execute/dry-run, q: back"),
                self.style.muted("(destroy is not available here -- use the Bash wizard's expert menu)"),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("up", "k"):
            self.selected_index = (self.selected_index - 1) % len(self.rows)
            # Arming is a decision about *this* row's action, not a
            # session-wide toggle. Unlike GuidedDeployScreen (one linear
            # "next step" target), this screen has many independently
            # selectable rows, so without disarming on navigation an
            # operator could arm intending to run one action, arrow to a
            # different row by mistake, and press enter to silently
            # execute the *wrong* app/action for real.
            self.armed = False
            return NavigationCommand.stay()
        if event.key in ("down", "j"):
            self.selected_index = (self.selected_index + 1) % len(self.rows)
            self.armed = False
            return NavigationCommand.stay()
        if event.key in ("a", "A"):
            self.toggle_armed()
            return NavigationCommand.stay()
        if event.key == "enter":
            self._run_selected()
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _run_selected(self) -> None:
        app_id, _label, action = self.rows[self.selected_index]
        executing = self.consume_arm()
        spec = self.catalog.app(app_id, action)
        self.last_execution = self.runner.run(spec, execute=executing)
