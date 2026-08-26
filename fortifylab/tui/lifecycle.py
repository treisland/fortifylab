"""Lifecycle workflow contracts for operation-backed TUI screens."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from fortifylab.operations import (
    OperationConfirmationRequired,
    OperationPreview,
    OperationRunResult,
    SensitiveRedactor,
    dry_run,
    run_operation,
)
from fortifylab.tui.workflows import WorkflowKeyResult


LifecycleStatus = Literal["preview", "requires_confirmation", "success", "failure", "blocked", "unsupported"]
LifecycleRunner = Callable[[str], OperationRunResult]


@dataclass(frozen=True)
class LifecycleActionContract:
    """Mapping from a navigation action target to catalog operation ids."""

    action_target: str
    label: str
    operation_ids: tuple[str, ...] = ()
    supported: bool = True
    unsupported_reason: str | None = None

    @property
    def default_operation_id(self) -> str | None:
        return self.operation_ids[0] if self.operation_ids else None


@dataclass(frozen=True)
class DryRunPreviewScreenModel:
    """Display contract for a lifecycle dry-run preview screen."""

    action_target: str
    operation_id: str
    label: str
    mutating: bool
    confirmation_required: bool
    commands: tuple[str, ...]
    confirmation_prompt: str | None


@dataclass(frozen=True)
class ExecutionResultDisplayModel:
    """Redacted execution result display contract for lifecycle operations."""

    status: LifecycleStatus
    operation_id: str | None
    exit_code: int | None
    stdout_summary: str
    stderr_summary: str
    redacted_output: tuple[str, ...]
    message: str


_COMPONENT_TARGETS: Mapping[str, str] = {
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "ssc": "SSC",
    "lim": "LIM",
    "scancentral_sast": "ScanCentral SAST",
    "scancentral_dast": "ScanCentral DAST",
}

_SAMPLE_TARGETS: Mapping[str, str] = {
    "juice_shop": "Juice Shop",
    "webgoat": "WebGoat",
    "dvwa": "DVWA",
}


def _app_contract(prefix: str, app_id: str, label: str) -> LifecycleActionContract:
    return LifecycleActionContract(
        action_target=f"{prefix}.{app_id}",
        label=label,
        operation_ids=(f"{app_id}.start", f"{app_id}.stop", f"{app_id}.destroy"),
    )


LIFECYCLE_ACTION_CONTRACTS: Mapping[str, LifecycleActionContract] = {
    "lifecycle.start_lab": LifecycleActionContract(
        "lifecycle.start_lab",
        "Start lab",
        ("lab.start.all",),
    ),
    "lifecycle.stop_lab": LifecycleActionContract(
        "lifecycle.stop_lab",
        "Stop lab",
        ("lab.stop.all",),
    ),
    "lifecycle.restart_lab": LifecycleActionContract(
        "lifecycle.restart_lab",
        "Restart lab",
        supported=False,
        unsupported_reason="Restart needs an ordered stop/start sequence screen in a later M9.4 slice.",
    ),
    "lifecycle.reset_lab": LifecycleActionContract(
        "lifecycle.reset_lab",
        "Reset lab",
        supported=False,
        unsupported_reason="Reset needs explicit destructive scope selection before it can execute.",
    ),
    **{
        f"app_lifecycle.{app_id}": _app_contract("app_lifecycle", app_id, label)
        for app_id, label in _COMPONENT_TARGETS.items()
    },
    **{
        f"app_lifecycle.{app_id}": _app_contract("app_lifecycle", app_id, label)
        for app_id, label in _SAMPLE_TARGETS.items()
    },
    **{
        f"sample_apps.{app_id}": _app_contract("sample_apps", app_id, label)
        for app_id, label in _SAMPLE_TARGETS.items()
    },
}


def lifecycle_workflow_targets() -> tuple[str, ...]:
    """Return navigation action targets owned by the lifecycle workflow."""

    return tuple(LIFECYCLE_ACTION_CONTRACTS)


def resolve_lifecycle_action(action_target: str) -> LifecycleActionContract:
    """Resolve a navigation action target to its lifecycle contract."""

    try:
        return LIFECYCLE_ACTION_CONTRACTS[action_target]
    except KeyError as exc:
        raise KeyError(f"Unknown lifecycle action target: {action_target}") from exc


def build_dry_run_preview(action_target: str, operation_id: str | None = None) -> DryRunPreviewScreenModel:
    """Build a dry-run preview model without executing lifecycle scripts."""

    contract = resolve_lifecycle_action(action_target)
    if not contract.supported or contract.default_operation_id is None:
        raise ValueError(contract.unsupported_reason or f"{action_target} is not supported")
    selected_operation_id = operation_id or contract.default_operation_id
    if selected_operation_id not in contract.operation_ids:
        raise ValueError(f"{selected_operation_id} is not valid for {action_target}")
    preview = dry_run(selected_operation_id)
    return _preview_model(action_target, preview)


def build_result_display(result: OperationRunResult) -> ExecutionResultDisplayModel:
    """Build the redacted result display model used by lifecycle screens."""

    redactor = SensitiveRedactor()
    stdout = "\n".join(redactor.text(command.stdout) for command in result.commands if command.stdout)
    stderr = "\n".join(redactor.text(command.stderr) for command in result.commands if command.stderr)
    output_lines: list[str] = []
    for command in result.commands:
        output_lines.append("$ " + " ".join(redactor.command(command.command)))
        if command.stdout:
            output_lines.extend(redactor.text(command.stdout).splitlines())
        if command.stderr:
            output_lines.extend(redactor.text(command.stderr).splitlines())

    status: LifecycleStatus = "success" if result.ok else "failure"
    return ExecutionResultDisplayModel(
        status=status,
        operation_id=result.operation_id,
        exit_code=result.exit_code,
        stdout_summary=_summarize_output(stdout),
        stderr_summary=_summarize_output(stderr),
        redacted_output=tuple(output_lines),
        message=(
            f"{result.operation_id} completed successfully."
            if result.ok
            else f"{result.operation_id} failed with exit code {result.exit_code}."
        ),
    )


def build_lifecycle_workflow(selected, runner: LifecycleRunner | None = None):  # type: ignore[no-untyped-def]
    """Build a lifecycle workflow screen for a selected navigation item."""

    return LifecycleWorkflowScreen(selected.action.target, selected.label, runner=runner)


class LifecycleWorkflowScreen:
    """Lifecycle screen with dry-run, confirmation, and operation runner hooks."""

    def __init__(
        self,
        action_target: str,
        title: str | None = None,
        *,
        runner: LifecycleRunner | None = None,
    ) -> None:
        self.contract = resolve_lifecycle_action(action_target)
        self.runner = runner or _confirmed_operation_runner
        self.selected_operation_id = self.contract.default_operation_id
        self.awaiting_confirmation = False
        self.last_preview: DryRunPreviewScreenModel | None = None
        self.last_result: ExecutionResultDisplayModel | None = None
        self.id = f"lifecycle:{action_target}"
        self.title = title or self.contract.label
        self.summary = f"{self.contract.label} lifecycle contract."
        self.lines = ()

    def render(self) -> str:
        lines = [self.summary]
        if not self.contract.supported:
            lines.append(f"Unsupported: {self.contract.unsupported_reason}")
            return "\n".join(lines)

        lines.append("Use Up/Down or 1-3 to select. p previews, c confirms, y runs, n cancels, b backs out.")
        lines.append("Operations:")
        for index, operation_id in enumerate(self.contract.operation_ids, start=1):
            marker = ">" if operation_id == self.selected_operation_id else " "
            lines.append(f"{marker} {index}. {operation_id}")
        lines.append("Preview before execution. Confirmation is required for mutating operations.")

        if self.last_preview is not None:
            lines.append("")
            lines.append(f"Dry run: {self.last_preview.operation_id}")
            lines.extend(f"  {command}" for command in self.last_preview.commands)
            if self.last_preview.confirmation_prompt:
                lines.append(f"Confirm: {self.last_preview.confirmation_prompt}")
        if self.last_result is not None:
            lines.append("")
            lines.append(f"Status: {self.last_result.status}")
            lines.append(self.last_result.message)
            if self.last_result.exit_code is not None:
                lines.append(f"Exit code: {self.last_result.exit_code}")
            if self.last_result.stdout_summary:
                lines.append(f"stdout: {self.last_result.stdout_summary}")
            if self.last_result.stderr_summary:
                lines.append(f"stderr: {self.last_result.stderr_summary}")
            if self.last_result.redacted_output:
                lines.append("Output:")
                lines.extend(f"  {line}" for line in self.last_result.redacted_output[:12])
                if len(self.last_result.redacted_output) > 12:
                    lines.append("  ...")
        return "\n".join(lines)

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"back", "b", "escape"}:
            return WorkflowKeyResult("Returned.", exit_screen=True)
        if not self.contract.supported:
            return WorkflowKeyResult(self.contract.unsupported_reason or "Lifecycle action is unsupported.")
        if key in {"up", "down"}:
            self._move_selection(-1 if key == "up" else 1)
            return WorkflowKeyResult(f"Selected {self.selected_operation_id}.")
        if key in {"1", "2", "3"}:
            index = int(key) - 1
            if index < len(self.contract.operation_ids):
                self._select_operation(index)
                return WorkflowKeyResult(f"Selected {self.selected_operation_id}.")
        if key in {"p", "d"}:
            self.last_preview = build_dry_run_preview(self.contract.action_target, self.selected_operation_id)
            self.awaiting_confirmation = False
            return WorkflowKeyResult(f"Previewed {self.last_preview.operation_id}.")
        if key in {"c", "enter"}:
            self.last_preview = build_dry_run_preview(self.contract.action_target, self.selected_operation_id)
            self.awaiting_confirmation = True
            self.last_result = ExecutionResultDisplayModel(
                status="requires_confirmation",
                operation_id=self.selected_operation_id,
                exit_code=None,
                stdout_summary="",
                stderr_summary="",
                redacted_output=(),
                message="Confirmation required before lifecycle execution.",
            )
            return WorkflowKeyResult(self.last_result.message)
        if key == "y" and self.awaiting_confirmation and self.selected_operation_id is not None:
            self.awaiting_confirmation = False
            self.last_result = _execute_with_runner(self.runner, self.selected_operation_id)
            return WorkflowKeyResult(self.last_result.message)
        if key in {"n", "cancel"} and self.awaiting_confirmation:
            self.awaiting_confirmation = False
            self.last_result = ExecutionResultDisplayModel(
                status="blocked",
                operation_id=self.selected_operation_id,
                exit_code=None,
                stdout_summary="",
                stderr_summary="",
                redacted_output=(),
                message="Lifecycle execution cancelled.",
            )
            return WorkflowKeyResult("Lifecycle execution cancelled.")
        return WorkflowKeyResult(f"No lifecycle action is bound to {key!r}.")


    def _select_operation(self, index: int) -> None:
        self.selected_operation_id = self.contract.operation_ids[index]
        self.awaiting_confirmation = False
        self.last_result = None
        self.last_preview = None

    def _move_selection(self, delta: int) -> None:
        if not self.contract.operation_ids:
            return
        try:
            current_index = self.contract.operation_ids.index(self.selected_operation_id or "")
        except ValueError:
            current_index = 0
        self._select_operation((current_index + delta) % len(self.contract.operation_ids))


def _preview_model(action_target: str, preview: OperationPreview) -> DryRunPreviewScreenModel:
    return DryRunPreviewScreenModel(
        action_target=action_target,
        operation_id=preview.operation_id,
        label=preview.label,
        mutating=preview.mutating,
        confirmation_required=preview.confirmation_required,
        commands=preview.commands,
        confirmation_prompt=preview.confirmation_prompt,
    )


def _execute_with_runner(runner: LifecycleRunner, operation_id: str) -> ExecutionResultDisplayModel:
    redactor = SensitiveRedactor()
    try:
        return build_result_display(runner(operation_id))
    except OperationConfirmationRequired as exc:
        return ExecutionResultDisplayModel(
            status="requires_confirmation",
            operation_id=operation_id,
            exit_code=None,
            stdout_summary="",
            stderr_summary="",
            redacted_output=(redactor.text(str(exc)),),
            message="Runner refused execution without confirmation.",
        )
    except Exception as exc:  # pragma: no cover - exact exception type belongs to future runners.
        return ExecutionResultDisplayModel(
            status="blocked",
            operation_id=operation_id,
            exit_code=None,
            stdout_summary="",
            stderr_summary=redactor.text(str(exc)),
            redacted_output=(redactor.text(str(exc)),),
            message="Lifecycle execution is blocked by the configured runner.",
        )


def _confirmed_operation_runner(operation_id: str) -> OperationRunResult:
    return run_operation(operation_id, confirmed=True)


def _summarize_output(output: str, *, limit: int = 160) -> str:
    collapsed = " ".join(line.strip() for line in output.splitlines() if line.strip())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."
