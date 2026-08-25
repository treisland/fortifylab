"""Operation adapter layer for the Python TUI migration."""

from __future__ import annotations

from .catalog import (
    OPERATION_CATALOG,
    OPERATION_ORDER,
    get_operation,
    list_operations,
    preview_operation,
)
from .models import (
    CommandExecutionResult,
    CommandPlan,
    Operation,
    OperationCategory,
    OperationPreview,
    OperationRunResult,
)
from .runner import (
    OperationConfirmationRequired,
    SensitiveRedactor,
    dry_run,
    run_command,
    run_operation,
)

__all__ = [
    "CommandExecutionResult",
    "CommandPlan",
    "OPERATION_CATALOG",
    "OPERATION_ORDER",
    "Operation",
    "OperationCategory",
    "OperationConfirmationRequired",
    "OperationPreview",
    "OperationRunResult",
    "SensitiveRedactor",
    "dry_run",
    "get_operation",
    "list_operations",
    "preview_operation",
    "run_command",
    "run_operation",
]
