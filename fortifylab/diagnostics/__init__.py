"""Read-only diagnostics contracts and doctor helpers."""

from __future__ import annotations

from .baseline import default_checks
from .doctor import DiagnosticRunner, build_clone_safe_doctor_report, doctor_command, render_doctor_report
from .models import (
    CheckStatus,
    DiagnosticCheck,
    DiagnosticCommandResult,
    DiagnosticResult,
    DiagnosticSection,
    DiagnosticSeverity,
    DiagnosticsBundleBoundary,
    DoctorReport,
)
from .redaction import redact_diagnostic_text

__all__ = [
    "CheckStatus",
    "DiagnosticCheck",
    "DiagnosticCommandResult",
    "DiagnosticResult",
    "DiagnosticRunner",
    "DiagnosticSection",
    "DiagnosticSeverity",
    "DiagnosticsBundleBoundary",
    "DoctorReport",
    "build_clone_safe_doctor_report",
    "default_checks",
    "doctor_command",
    "redact_diagnostic_text",
    "render_doctor_report",
]
