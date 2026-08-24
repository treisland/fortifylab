"""Lab Status Dashboard screen -- the interactive replacement for the
readiness board (``setup_readiness_items()`` / ``setup_readiness_score()``)
in ``scripts/wizard/setup.sh``.

Entirely read-only, like Diagnostics/Runbooks/Help: no arming step,
because this screen never mutates anything, only reports. Checks run on
open and can be re-run with ``r`` (matching Bash, where the board simply
redraws each time the setup menu is shown).

Not wired: any repair action. Bash's board is read-only too -- fixing a
`warn` item happens elsewhere in the wizard (Configuration editor, TLS
setup, etc.), and that stays true here as well.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fortifylab.services.lab_status_service import LabStatusService, ReadinessCheck

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


@dataclass
class DashboardScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: LabStatusService = field(default_factory=LabStatusService)
    checks: tuple[ReadinessCheck, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.checks:
            self.checks = self.service.readiness()

    def render(self) -> str:
        lines = [self.style.heading("Lab Status Dashboard"), ""]
        ready_count = sum(1 for check in self.checks if check.ready)
        lines.append(f"Readiness: {ready_count}/{len(self.checks)}")
        lines.append("")
        for check in self.checks:
            marker_text = f"{'ready' if check.ready else 'warn':<12}"
            marker = self.style.ok(marker_text) if check.ready else self.style.fail(marker_text)
            line = f"  {marker} {check.label}"
            if not check.ready and check.detail:
                line += f" -- {check.detail}"
            lines.append(line)

        first_warn = next((check for check in self.checks if not check.ready), None)
        lines.append("")
        if first_warn is None:
            lines.append(self.style.ok("Recommended next action: none -- everything checked is ready."))
        else:
            lines.append(f"Recommended next action: {first_warn.detail}")

        lines.extend(("", self.style.muted("r: re-run checks, q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("r", "R"):
            self.checks = self.service.readiness()
            return NavigationCommand.stay()
        return NavigationCommand.stay()
