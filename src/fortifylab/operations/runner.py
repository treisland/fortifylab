"""Safe operation runner with dry-run default and execution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fortifylab.core.command import CommandResult, redact_text, run_command
from fortifylab.runtime import write_runtime_log

from .catalog import OperationImpact, OperationSpec


Runner = Callable[[tuple[str, ...]], CommandResult]


@dataclass(frozen=True)
class OperationExecution:
    operation_id: str
    command: tuple[str, ...]
    executed: bool
    ok: bool
    detail: str
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float = 0
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    log_file: str | None = None

    def summary(self, *, limit: int = 1200) -> str:
        return summarize_output(self.detail, limit=limit)


class OperationRunner:
    def __init__(self, runner: Runner | None = None, *, timeout: float = 600) -> None:
        self.timeout = timeout
        self.runner = runner or (lambda command: self._default_runner(command, timeout=self.timeout))

    def run(self, spec: OperationSpec, *, execute: bool = False, confirmation: str | None = None) -> OperationExecution:
        if spec.mutates and not execute:
            return OperationExecution(spec.operation_id, spec.command, False, True, "Dry run; pass execute=True to run this mutating operation.")
        if spec.confirmation_phrase and confirmation != spec.confirmation_phrase:
            kind = "Destructive operation" if spec.impact is OperationImpact.DESTRUCTIVE else "Operation"
            return OperationExecution(spec.operation_id, spec.command, False, False, f"{kind} requires confirmation: {spec.confirmation_phrase}")
        started = datetime.now(timezone.utc).isoformat()
        log_file = write_runtime_log(f"operation {spec.operation_id} started", event="operation.start")
        try:
            result = self.runner(spec.command)
        except OSError as exc:
            result = CommandResult(spec.command, 127, "", str(exc), 0)
        ended = datetime.now(timezone.utc).isoformat()
        stdout = redact_text(result.stdout)
        stderr = redact_text(result.stderr)
        detail = summarize_output(stdout if result.ok else stderr or stdout)
        write_runtime_log(f"operation {spec.operation_id} completed returncode={result.returncode}", event="operation.end")
        return OperationExecution(
            operation_id=spec.operation_id,
            command=spec.command,
            executed=True,
            ok=result.ok,
            detail=detail,
            started_at=started,
            ended_at=ended,
            duration_seconds=result.duration_seconds,
            returncode=result.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=result.timed_out,
            log_file=str(log_file),
        )

    @staticmethod
    def _default_runner(command: tuple[str, ...], *, timeout: float = 600) -> CommandResult:
        return run_command(command, timeout=timeout)


def summarize_output(text: str, *, limit: int = 1200) -> str:
    redacted = redact_text(text).strip()
    if len(redacted) <= limit:
        return redacted
    omitted = len(redacted) - limit
    return f"{redacted[:limit].rstrip()}\n... <{omitted} characters omitted>"
