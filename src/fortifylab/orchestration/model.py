"""Deployment plan and status models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DeploymentStep:
    step_id: str
    label: str
    command: tuple[str, ...]
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: int = 600
    optional: bool = False


@dataclass(frozen=True)
class OperationState:
    step_id: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    detail: str = ""


@dataclass(frozen=True)
class DeploymentPlan:
    name: str
    steps: tuple[DeploymentStep, ...]

    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.steps)

    def validate(self) -> tuple[str, ...]:
        known = set(self.step_ids())
        errors: list[str] = []
        for step in self.steps:
            for dependency in step.dependencies:
                if dependency not in known:
                    errors.append(f"{step.step_id} depends on unknown step {dependency}")
        return tuple(errors)

    def runnable_steps(self, states: dict[str, OperationState]) -> tuple[DeploymentStep, ...]:
        runnable: list[DeploymentStep] = []
        for step in self.steps:
            state = states.get(step.step_id, OperationState(step.step_id))
            if state.status is not StepStatus.PENDING:
                continue
            dependencies_complete = all(
                states.get(dep, OperationState(dep)).status is StepStatus.COMPLETE
                for dep in step.dependencies
            )
            if dependencies_complete:
                runnable.append(step)
        return tuple(runnable)
