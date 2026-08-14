"""Security helpers for the Fortify Lab web console."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fortifylab.core.command import redact_text


REDACTED = "<redacted>"


@dataclass(frozen=True)
class ActionSecurityMode:
    """Describe whether web-triggered actions are available."""

    enable_actions: bool = False

    @property
    def mode(self) -> str:
        return "actions_enabled" if self.enable_actions else "read_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "read_only": not self.enable_actions,
            "enable_actions": self.enable_actions,
        }


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    return value


def redacted_command(command: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(redact_value(part)) for part in command)


def confirmation_contract(phrase: str | None) -> dict[str, Any]:
    return {
        "required": bool(phrase),
        "phrase": phrase,
        "comparison": "exact",
        "case_sensitive": True,
    }
