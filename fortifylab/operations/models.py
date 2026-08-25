"""Operation model contracts for Bash-backed lifecycle adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OperationCategory(str, Enum):
    """High-level groups used by the TUI and tests."""

    LAB_LIFECYCLE = "lab_lifecycle"
    COMPONENT = "component"
    SAMPLE_APP = "sample_app"
    SUPPORT = "support"


@dataclass(frozen=True)
class CommandPlan:
    """A command the operation runner may execute after confirmation."""

    argv: tuple[str, ...]
    label: str | None = None
    cwd: Path | None = None

    def preview(self) -> str:
        return " ".join(self.argv)


@dataclass(frozen=True)
class Operation:
    """Catalog entry for one safe, previewable operation."""

    id: str
    label: str
    category: OperationCategory
    command_plan: tuple[CommandPlan, ...]
    mutating: bool
    confirmation_required: bool
    description: str = ""
    confirmation_prompt: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.mutating and not self.confirmation_required:
            raise ValueError(f"Mutating operation {self.id!r} must require confirmation")


@dataclass(frozen=True)
class OperationPreview:
    """Dry-run representation safe for display in the TUI."""

    operation_id: str
    label: str
    mutating: bool
    confirmation_required: bool
    commands: tuple[str, ...]
    confirmation_prompt: str | None = None


@dataclass(frozen=True)
class CommandExecutionResult:
    """Result for a single command execution."""

    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass(frozen=True)
class OperationRunResult:
    """Aggregate result for an operation run."""

    operation_id: str
    exit_code: int
    commands: tuple[CommandExecutionResult, ...]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0
