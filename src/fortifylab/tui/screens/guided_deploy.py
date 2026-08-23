"""Guided deployment screen -- the interactive replacement for
``guided_deployment_menu()`` / the guided loop in ``scripts/wizard/guided.sh``,
for the one profile (SSC-only) the deploy service currently drives.

Dry-run is the default and stays repeatable; execution requires explicitly
arming the screen first ("a"), the same dry-run-unless-told-otherwise
posture every other operation in this codebase takes (see
``OperationCatalog``/``OperationRunner``'s ``execute`` flag).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fortifylab.orchestration import OperationResult, StepStatus
from fortifylab.services.deploy_service import DeployService

from ..events import Event, KeyEvent, TickEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen

_STATUS_SYMBOLS = {
    StepStatus.COMPLETE: "ok",
    StepStatus.FAILED: "fail",
    StepStatus.CANCELLED: "fail",
    StepStatus.RUNNING: "running",
}


@dataclass
class GuidedDeployScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: DeployService = field(default_factory=DeployService)
    armed: bool = False
    last_result: OperationResult | None = None
    ticks: int = 0

    def render(self) -> str:
        lines = [self.style.heading(f"Guided deployment -- {self.service.plan.name}"), ""]
        for step in self.service.plan.steps:
            status = self.service.states[step.step_id].status
            marker = self.style.symbol(_STATUS_SYMBOLS.get(status, "next" if status is StepStatus.PENDING else "-"))
            lines.append(f"  {marker} {step.label:<32} {status.value}")
        lines.append("")
        mode_label = "EXECUTE (armed)" if self.armed else "dry-run (preview only)"
        lines.append(f"Mode: {mode_label}")
        if self.last_result is not None:
            lines.append(f"Last: {self.last_result.detail}")
        if self.service.is_complete:
            lines.append("")
            lines.append(self.style.ok("All steps complete."))
        elif self.service.has_failed:
            lines.append("")
            lines.append(self.style.fail("A step failed -- see detail above."))
        lines.extend(
            (
                "",
                self.style.muted("enter: run next step   a: toggle execute/dry-run   q: back"),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if isinstance(event, TickEvent):
            self.ticks += 1
            return NavigationCommand.stay()
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("a", "A"):
            self.armed = not self.armed
            return NavigationCommand.stay()
        if event.key == "enter":
            self.last_result = self.service.run_next(execute=self.armed)
            return NavigationCommand.stay()
        return NavigationCommand.stay()
