"""Resumable guided deployment session metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .model import OperationState, StepStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class GuidedSession:
    session_id: str
    profile_id: str
    current_step: str
    auto_advance: bool = False
    states: dict[str, OperationState] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now_iso)

    def mark(self, step_id: str, status: StepStatus, detail: str = "") -> "GuidedSession":
        next_states = dict(self.states)
        previous = next_states.get(step_id, OperationState(step_id))
        next_states[step_id] = OperationState(
            step_id=step_id,
            status=status,
            attempts=previous.attempts + 1,
            detail=detail,
        )
        return GuidedSession(
            session_id=self.session_id,
            profile_id=self.profile_id,
            current_step=step_id,
            auto_advance=self.auto_advance,
            states=next_states,
        )

    def to_record(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "current_step": self.current_step,
            "auto_advance": self.auto_advance,
            "updated_at": self.updated_at,
            "states": {
                key: {
                    "status": value.status.value,
                    "attempts": value.attempts,
                    "detail": value.detail,
                }
                for key, value in self.states.items()
            },
        }
