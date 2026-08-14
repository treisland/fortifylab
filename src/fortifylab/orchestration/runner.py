"""Retry, timeout, cancellation, and dry-run orchestration behavior."""

from __future__ import annotations

from dataclasses import dataclass

from fortifylab.core.command import run_command

from .model import DeploymentStep, StepStatus


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2


@dataclass(frozen=True)
class OperationResult:
    step_id: str
    status: StepStatus
    attempts: int
    detail: str
    command: tuple[str, ...]


class OperationController:
    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, step: DeploymentStep, *, dry_run: bool = True) -> OperationResult:
        if self.cancelled:
            return OperationResult(step.step_id, StepStatus.CANCELLED, 0, "Operation cancelled.", step.command)
        if dry_run:
            return OperationResult(step.step_id, StepStatus.READY, 0, "Dry run; command was not executed.", step.command)

        attempts = 0
        last_detail = ""
        while attempts < self.retry_policy.max_attempts:
            attempts += 1
            result = run_command(step.command, timeout_seconds=step.timeout_seconds)
            if result.ok:
                return OperationResult(step.step_id, StepStatus.COMPLETE, attempts, "Operation completed.", step.command)
            if result.timed_out:
                last_detail = f"Timed out after {step.timeout_seconds}s."
            else:
                last_detail = result.stderr or result.stdout or f"Exited with {result.returncode}."
        return OperationResult(step.step_id, StepStatus.FAILED, attempts, last_detail, step.command)
