"""Safe operation runner with dry-run default."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fortifylab.core.command import CommandResult, run_command

from .catalog import OperationImpact, OperationSpec


Runner = Callable[[tuple[str, ...]], CommandResult]


@dataclass(frozen=True)
class OperationExecution:
    operation_id: str
    command: tuple[str, ...]
    executed: bool
    ok: bool
    detail: str


class OperationRunner:
    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or self._default_runner

    def run(self, spec: OperationSpec, *, execute: bool = False, confirmation: str | None = None) -> OperationExecution:
        if spec.impact is OperationImpact.DESTRUCTIVE and confirmation != spec.confirmation_phrase:
            return OperationExecution(spec.operation_id, spec.command, False, False, f"Destructive operation requires confirmation: {spec.confirmation_phrase}")
        if spec.mutates and not execute:
            return OperationExecution(spec.operation_id, spec.command, False, True, "Dry run; pass execute=True to run this mutating operation.")
        result = self.runner(spec.command)
        detail = result.stdout if result.ok else result.stderr or result.stdout
        return OperationExecution(spec.operation_id, spec.command, True, result.ok, detail)

    @staticmethod
    def _default_runner(command: tuple[str, ...]) -> CommandResult:
        return run_command(command, timeout_seconds=600)
