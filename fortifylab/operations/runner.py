"""Safe command runner for operation catalog entries."""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence

from fortifylab.paths import repo_root

from .catalog import get_operation, operation_preview
from .models import (
    CommandExecutionResult,
    CommandPlan,
    Operation,
    OperationPreview,
    OperationRunResult,
)


class OperationConfirmationRequired(RuntimeError):
    """Raised when a mutating operation is executed without confirmation."""


class SensitiveRedactor:
    """Redact secrets and local sensitive paths from commands and output."""

    _KEY_VALUE_PATTERN = re.compile(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key|license)\b\s*[:=]\s*([^\s]+)"
    )
    _BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
    _SENSITIVE_PATH_PATTERN = re.compile(
        r"(?P<path>(?:/[^/\s]+)+/(?:\.ssh|secrets|certs|\.env)(?:/[^\s]*)?)"
    )

    def __init__(self, *, extra_values: Iterable[str] = ()) -> None:
        self._repo_root = str(repo_root())
        self._home = os.path.expanduser("~")
        self._extra_values = tuple(value for value in extra_values if value)

    def text(self, value: str) -> str:
        redacted = value.replace(self._repo_root, "<repo>")
        if self._home != "/":
            redacted = redacted.replace(self._home, "<home>")
        for secret in self._extra_values:
            redacted = redacted.replace(secret, "<redacted>")
        redacted = self._KEY_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
        redacted = self._BEARER_PATTERN.sub("Bearer <redacted>", redacted)
        redacted = self._SENSITIVE_PATH_PATTERN.sub("<sensitive-path>", redacted)
        return redacted

    def command(self, argv: Sequence[str]) -> tuple[str, ...]:
        return tuple(self.text(part) for part in argv)


def dry_run(operation_or_id: str | Operation) -> OperationPreview:
    """Return a redacted operation preview without executing commands."""

    operation = get_operation(operation_or_id) if isinstance(operation_or_id, str) else operation_or_id
    preview = operation_preview(operation)
    redactor = SensitiveRedactor()
    return OperationPreview(
        operation_id=preview.operation_id,
        label=preview.label,
        mutating=preview.mutating,
        confirmation_required=preview.confirmation_required,
        commands=tuple(redactor.text(command) for command in preview.commands),
        confirmation_prompt=preview.confirmation_prompt,
    )


def run_operation(
    operation_or_id: str | Operation,
    *,
    confirmed: bool = False,
    env: Mapping[str, str] | None = None,
    redactor: SensitiveRedactor | None = None,
) -> OperationRunResult:
    """Run an operation after enforcing the confirmation gate."""

    operation = get_operation(operation_or_id) if isinstance(operation_or_id, str) else operation_or_id
    if operation.confirmation_required and not confirmed:
        raise OperationConfirmationRequired(operation.confirmation_prompt or operation.label)

    active_redactor = redactor or SensitiveRedactor()
    results: list[CommandExecutionResult] = []
    exit_code = 0
    for command in operation.command_plan:
        result = run_command(command, env=env, redactor=active_redactor)
        results.append(result)
        if result.exit_code != 0:
            exit_code = result.exit_code
            break
    return OperationRunResult(operation_id=operation.id, exit_code=exit_code, commands=tuple(results))


def run_command(
    command: CommandPlan,
    *,
    env: Mapping[str, str] | None = None,
    redactor: SensitiveRedactor | None = None,
) -> CommandExecutionResult:
    """Execute one command plan and return a redacted result."""

    active_redactor = redactor or SensitiveRedactor()
    started = time.monotonic()
    completed = subprocess.run(
        command.argv,
        cwd=command.cwd,
        env=None if env is None else {**os.environ, **env},
        text=True,
        capture_output=True,
        check=False,
    )
    duration = time.monotonic() - started
    return CommandExecutionResult(
        command=active_redactor.command(command.argv),
        exit_code=completed.returncode,
        stdout=active_redactor.text(completed.stdout),
        stderr=active_redactor.text(completed.stderr),
        duration_seconds=duration,
    )
