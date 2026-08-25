"""Guided deployment screen -- the interactive replacement for
``guided_deployment_menu()`` / the guided loop in ``scripts/wizard/guided.sh``,
for the one profile (SSC-only) the deploy service currently drives.

Dry-run is the default and stays repeatable; execution requires explicitly
arming the screen first ("a"), the same dry-run-unless-told-otherwise
posture every other operation in this codebase takes (see
``OperationCatalog``/``OperationRunner``'s ``execute`` flag).

Once armed, though, arming stays on and drives the *whole remaining plan*
step by step -- unlike ``Armable.consume_arm()``'s one-shot-then-disarm
posture elsewhere (``ApplicationsScreen``'s start/stop/destroy, where
arming is a decision about one action), matching Bash's own guided
auto-advance ("stopping only for required manual input or a failure").
A failed step disarms automatically; the operator can also disarm ("a")
at any time to pause after the step currently running finishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fortifylab.orchestration import OperationResult, StepStatus
from fortifylab.services.deploy_service import DeployService

from ..events import Event, KeyEvent, TickEvent
from ..theme import TerminalStyle
from .base import Armable, NavigationCommand, Screen

# Symbol + color per status, matching scripts/wizard/guided.sh's own
# guided_status_render() convention (complete=green, in_progress=yellow,
# failed=red, pending=yellow, manual/skipped=dim). STEP_STATUS.READY only
# exists on the Python side (a dry-run preview marker, not a real Bash
# status) and is styled as muted rather than borrowing any of those.
_STATUS_SYMBOLS = {
    StepStatus.COMPLETE: "ok",
    StepStatus.FAILED: "fail",
    StepStatus.CANCELLED: "fail",
    StepStatus.RUNNING: "running",
    StepStatus.PENDING: "next",
    StepStatus.READY: "next",
    StepStatus.SKIPPED: "next",
}
_STATUS_COLORS = {
    StepStatus.COMPLETE: "ok",
    StepStatus.FAILED: "fail",
    StepStatus.CANCELLED: "fail",
    # RUNNING used to share PENDING's color (warn/yellow) -- the "●"
    # symbol still differed, but at a glance a step that had actually
    # started looked the same shade as every step still waiting behind
    # it, which read as "is this stuck?" (bug report). RUNNING now gets
    # its own color (cyan) so an in-progress step is visually distinct
    # from steps not yet reached.
    StepStatus.RUNNING: "running",
    StepStatus.PENDING: "warn",
    StepStatus.READY: "muted",
    StepStatus.SKIPPED: "muted",
}


@dataclass
class GuidedDeployScreen(Armable, Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: DeployService = field(default_factory=DeployService)
    last_result: OperationResult | None = None
    ticks: int = 0

    def render(self) -> str:
        lines = [self.style.heading(f"Guided deployment -- {self.service.plan.name}"), ""]
        for step in self.service.plan.steps:
            status = self.service.states[step.step_id].status
            marker = self.style.symbol(_STATUS_SYMBOLS.get(status, "-"))
            colorize = getattr(self.style, _STATUS_COLORS.get(status, "muted"))
            # Pad the plain text to width first, then colorize the whole
            # row -- coloring first and padding after would count the ANSI
            # escape sequence's own characters toward the field width and
            # break column alignment (see the M12 Dashboard fix).
            plain_row = f"{marker} {step.label:<32} {status.value}"
            lines.append(f"  {colorize(plain_row)}")
        lines.append("")
        lines.append(f"Mode: {self.mode_label()}")
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
                self.style.muted("enter: run next step   a: arm auto-advance (runs until done or failed)   q: back"),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if isinstance(event, TickEvent):
            self.ticks += 1
            # Pick up a background execution's result once it's ready --
            # see DeployService.start_execute()/poll_execute(). A no-op
            # (returns None immediately) whenever nothing is executing.
            result = self.service.poll_execute()
            if result is not None:
                self.last_result = result
                if result.status in (StepStatus.FAILED, StepStatus.CANCELLED):
                    # Matches Bash's own guided auto-advance: "stopping
                    # only for required manual input or a failure" -- a
                    # failed step must not silently keep going into the
                    # next one.
                    self.armed = False
                elif self.armed:
                    # Once armed, keep driving the plan forward step by
                    # step without needing "a" pressed again before every
                    # single enter -- this is the same "one confirmation,
                    # then unattended until done or failed" flow Bash's
                    # guided_deployment_menu()'s auto-advance offers (bug
                    # report: "why not automatic"). start_execute() is a
                    # no-op once nothing is left runnable.
                    self.service.start_execute()
            return NavigationCommand.stay()
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("a", "A"):
            self.toggle_armed()
            return NavigationCommand.stay()
        if event.key == "enter":
            if self.service.is_executing:
                return NavigationCommand.stay()
            if self.armed:
                # Real execution runs on a background thread so this
                # screen can show "running" on the very next render
                # instead of freezing until the (possibly minutes-long)
                # subprocess returns -- see the bug report. The result
                # arrives via a TickEvent above, which also keeps driving
                # the remaining steps forward automatically while armed
                # stays True (see the TickEvent branch) -- unlike
                # Armable.consume_arm()'s one-shot-then-disarm posture
                # elsewhere (start/stop/destroy), arming here means "run
                # this whole plan," not "run one action," matching Bash.
                self.service.start_execute()
                return NavigationCommand.stay()
            result = self.service.run_next(execute=False)
            if result is not None:
                self.last_result = result
            return NavigationCommand.stay()
        return NavigationCommand.stay()
