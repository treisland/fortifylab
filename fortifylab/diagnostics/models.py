"""Read-only diagnostics contracts for Fortify Lab."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


class DiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DiagnosticCheck:
    id: str
    label: str
    category: str
    severity: DiagnosticSeverity = DiagnosticSeverity.INFO
    command: tuple[str, ...] = ()
    requires_network: bool = False
    mutating: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if self.mutating:
            raise ValueError(f"Diagnostic check {self.id!r} must be read-only")


@dataclass(frozen=True)
class DiagnosticCommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class DiagnosticResult:
    check_id: str
    status: CheckStatus
    severity: DiagnosticSeverity
    summary: str
    detail: str = ""
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is CheckStatus.PASS


@dataclass(frozen=True)
class DiagnosticSection:
    name: str
    results: tuple[DiagnosticResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DoctorReport:
    title: str
    sections: tuple[DiagnosticSection, ...]

    @property
    def ok(self) -> bool:
        return all(result.status is CheckStatus.PASS for section in self.sections for result in section.results)

    @property
    def has_warnings_or_failures(self) -> bool:
        return any(result.status in {CheckStatus.WARN, CheckStatus.FAIL} for section in self.sections for result in section.results)


@dataclass(frozen=True)
class DiagnosticsBundleBoundary:
    included: tuple[str, ...]
    excluded: tuple[str, ...]
    redaction_required: bool = True
