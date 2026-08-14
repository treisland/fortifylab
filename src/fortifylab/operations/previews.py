"""Allowlisted operation previews for web lifecycle actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import OperationCatalog, OperationSpec
from .security import confirmation_contract, redacted_command


@dataclass(frozen=True)
class ActionPreview:
    operation: OperationSpec
    execution_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        spec = self.operation
        return {
            "id": spec.operation_id,
            "label": spec.label,
            "kind": spec.kind.value,
            "impact": spec.impact.value,
            "mutates": spec.mutates,
            "allowed": True,
            "execution_enabled": self.execution_enabled,
            "command": list(redacted_command(spec.command)),
            "command_display": " ".join(redacted_command(spec.command)),
            "warning": spec.warning,
            "confirmation": confirmation_contract(spec.confirmation_phrase),
        }


class ActionPreviewCatalog:
    """Expose only known-safe operation preview entries to web clients."""

    def __init__(self, catalog: OperationCatalog | None = None, *, enable_actions: bool = False) -> None:
        self.catalog = catalog or OperationCatalog()
        self.enable_actions = enable_actions

    def list(self) -> tuple[ActionPreview, ...]:
        return tuple(ActionPreview(spec, self.enable_actions and spec.mutates) for spec in self._allowlisted_operations())

    def get(self, operation_id: str) -> ActionPreview | None:
        for preview in self.list():
            if preview.operation.operation_id == operation_id:
                return preview
        return None

    def _allowlisted_operations(self) -> tuple[OperationSpec, ...]:
        return (
            self.catalog.certs(),
            self.catalog.secrets(),
            self.catalog.app("ssc", "start"),
            self.catalog.app("ssc", "stop"),
            self.catalog.app("ssc", "destroy"),
            self.catalog.logs("ssc-webapp-0", follow=False),
            self.catalog.runbook("first-scan"),
        )
