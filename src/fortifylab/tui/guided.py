"""Small guided deployment TUI model for the Phase 3.2 prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class StepState(str, Enum):
    """User-facing state for a guided deployment step."""

    PENDING = "pending"
    IN_PROGRESS = "in progress"
    COMPLETE = "complete"
    FAILED = "failed"
    MANUAL = "manual"
    SKIPPED = "skipped"


class ControlMode(str, Enum):
    """How the wizard should proceed after a step refresh."""

    INTERACTIVE = "interactive"
    AUTO_ADVANCE = "auto-advance"


@dataclass(frozen=True)
class GuidedStep:
    """Static guided deployment step metadata."""

    step_id: str
    label: str
    help_text: str
    optional: bool = False
    manual: bool = False
    log_scope: str | None = None


@dataclass(frozen=True)
class StepSnapshot:
    """Current rendered state for one guided deployment step."""

    step: GuidedStep
    index: int
    total: int
    state: StepState
    detail: str
    elapsed_seconds: int = 0
    timeout_seconds: int | None = None
    probe: str | None = None
    pods: tuple[str, ...] = field(default_factory=tuple)
    events: tuple[str, ...] = field(default_factory=tuple)
    mode: ControlMode = ControlMode.INTERACTIVE
    next_step_label: str | None = None
    auto_advance_seconds: int = 5
    refresh_seconds: int = 5

    @property
    def has_logs(self) -> bool:
        return bool(self.step.log_scope)

    @property
    def auto_advance_available(self) -> bool:
        return self.mode is ControlMode.AUTO_ADVANCE and self.state is StepState.COMPLETE


def _format_elapsed(snapshot: StepSnapshot) -> str:
    if snapshot.timeout_seconds is None:
        return f"{snapshot.elapsed_seconds}s"
    return f"{snapshot.elapsed_seconds}s / {snapshot.timeout_seconds}s"


def _lines_or_default(lines: Iterable[str], default: str) -> list[str]:
    rendered = [line for line in lines if line]
    return rendered or [default]


def render_guided_step(snapshot: StepSnapshot) -> str:
    """Render a stable guided-step screen without terminal clear commands."""

    title = f"Guided deployment - Step {snapshot.index} of {snapshot.total}"
    lines = [
        title,
        "-" * min(78, len(title) + 42),
        "",
        snapshot.step.label,
        "",
        snapshot.step.help_text,
        "",
        f"State:   {snapshot.state.value}",
    ]
    if snapshot.probe:
        lines.append(f"Probe:   {snapshot.probe}")
    lines.extend(
        [
            f"Elapsed: {_format_elapsed(snapshot)}",
            f"Detail:  {snapshot.detail}",
            "",
            "Pods",
        ]
    )
    lines.extend(f"  {line}" for line in _lines_or_default(snapshot.pods, "No pod status applies to this step yet."))
    lines.extend(["", "Recent events"])
    lines.extend(f"  {line}" for line in _lines_or_default(snapshot.events, "No recent events reported yet."))
    lines.extend(["", _control_line(snapshot), _status_line(snapshot)])
    return "\n".join(lines).rstrip() + "\n"


def _control_line(snapshot: StepSnapshot) -> str:
    controls = ["r. Retry operation", "i. Take interactive control", "b. Back"]
    if snapshot.has_logs:
        controls.append("p. Pod logs")
    controls.extend(["d. Diagnostics", "q. Quit safely"])
    return "   ".join(controls)


def _status_line(snapshot: StepSnapshot) -> str:
    if snapshot.auto_advance_available:
        next_label = snapshot.next_step_label or "the next step"
        return (
            f"Continuing to {next_label} in {snapshot.auto_advance_seconds}s. "
            "Press i for interactive control."
        )
    if snapshot.mode is ControlMode.AUTO_ADVANCE:
        return (
            f"Waiting {snapshot.refresh_seconds}s before the next refresh. "
            "Press i for interactive control."
        )
    return "Interactive mode. Choose an action."


def build_demo_snapshot() -> StepSnapshot:
    """Return a deterministic prototype screen for CLI previews and tests."""

    return StepSnapshot(
        step=GuidedStep(
            step_id="ssc",
            label="Verifying Software Security Center",
            help_text="Waiting for SSC StatefulSet readiness and the application endpoint.",
            log_scope="ssc-webapp*",
        ),
        index=9,
        total=13,
        state=StepState.IN_PROGRESS,
        probe="ssc_ready",
        detail="Ingress, service endpoints, and HTTP readiness are still being checked.",
        elapsed_seconds=45,
        timeout_seconds=900,
        pods=("ssc-webapp-0                         0/1      Running",),
        events=("Normal   Pulled    pod/ssc-webapp-0   Container image is present",),
        mode=ControlMode.AUTO_ADVANCE,
        next_step_label="LIM",
    )


def step_snapshot_from_live(
    live_step,
    *,
    index: int,
    total: int,
    mode: ControlMode = ControlMode.INTERACTIVE,
) -> StepSnapshot:
    """Convert a live status step into the existing guided-step renderer model."""

    state_map = {
        "pending": StepState.PENDING,
        "in_progress": StepState.IN_PROGRESS,
        "complete": StepState.COMPLETE,
        "failed": StepState.FAILED,
        "blocked": StepState.FAILED,
        "unknown": StepState.PENDING,
    }
    pods = tuple(f"{pod.name:<36} {pod.ready}/{pod.total}      {pod.phase}" for pod in live_step.pods)
    events = tuple(f"{event.type:<8} {event.reason:<18} {event.object}   {event.message}" for event in live_step.events)
    hints = "; ".join(hint.message for hint in live_step.hints)
    detail = f"{live_step.detail} {hints}".strip()
    return StepSnapshot(
        step=GuidedStep(step_id=live_step.step_id, label=live_step.label, help_text=detail, log_scope=f"{live_step.step_id}*"),
        index=index,
        total=total,
        state=state_map.get(getattr(live_step.state, "value", str(live_step.state)), StepState.PENDING),
        detail=detail,
        elapsed_seconds=live_step.elapsed_seconds,
        timeout_seconds=live_step.timeout_seconds,
        pods=pods,
        events=events,
        mode=mode,
    )
