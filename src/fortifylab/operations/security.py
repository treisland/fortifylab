"""Shared operation security helpers."""

from __future__ import annotations

from typing import Any

from fortifylab.core.command import redact_text


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
