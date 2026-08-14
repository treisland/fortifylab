"""Safe operation runner with dry-run default and execution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fortifylab.core.command import CommandResult, run_command
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


class OperationRunner:
    def __init__(self, runner: Runner | None = None, *, timeout: float = 600) -> None:
        self.runner = runner or self._default_runner
        self.timeout = timeout

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
        detail = result.stdout if result.ok else result.stderr or result.stdout
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
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            log_file=str(log_file),
        )

    @staticmethod
    def _default_runner(command: tuple[str, ...]) -> CommandResult:
        return run_command(command, timeout=600)
