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
    get_operation,
    run_operation,
)
from fortifylab.tui.workflows import WorkflowKeyResult


LifecycleStatus = Literal["preview", "requires_confirmation", "success", "failure", "blocked", "unsupported"]
LifecycleDataImpact = Literal["none", "retained", "review", "deleted"]
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


@dataclass(frozen=True)
class LifecycleScope:
    """A lifecycle target scope before it is expanded into operations."""

    id: str
    label: str
    component_ids: tuple[str, ...]
    profile_id: str | None = None
    description: str = ""


@dataclass(frozen=True)
class LifecycleActionOption:
    """User-facing lifecycle action available for a target scope."""

    id: str
    label: str
    description: str
    data_impact: LifecycleDataImpact
    destructive: bool = False
    available: bool = True
    unavailable_reason: str | None = None
    confirmation_phrase: str | None = None


@dataclass(frozen=True)
class LifecyclePlanStep:
    """One operation step in a lifecycle plan."""

    component_id: str
    label: str
    operation_id: str
    order: int
    data_impact: LifecycleDataImpact


@dataclass(frozen=True)
class LifecycleHandoff:
    """Post-run or inspection handoff shown from lifecycle screens."""

    key: str
    label: str
    workflow_target: str
    summary: str


@dataclass(frozen=True)
class LifecyclePlan:
    """Clone-safe lifecycle plan contract; building it never executes scripts."""

    action_id: str
    label: str
    scope: LifecycleScope
    steps: tuple[LifecyclePlanStep, ...]
    data_impact: LifecycleDataImpact
    destructive: bool
    confirmation_phrase: str | None
    order_note: str
    handoffs: tuple[LifecycleHandoff, ...]

    @property
    def operation_ids(self) -> tuple[str, ...]:
        return tuple(step.operation_id for step in self.steps)


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


_FULL_LAB_COMPONENT_ORDER: tuple[str, ...] = (
    "mysql",
    "postgresql",
    "ssc",
    "lim",
    "scancentral_sast",
    "scancentral_dast",
)

_PROFILE_SCOPE_COMPONENTS: Mapping[str, tuple[str, ...]] = {
    "core": _FULL_LAB_COMPONENT_ORDER,
    "sast_full": ("mysql", "postgresql", "ssc", "lim", "scancentral_sast", "juice_shop"),
    "dast_full": ("mysql", "postgresql", "ssc", "lim", "scancentral_dast", "juice_shop", "webgoat", "dvwa"),
    "ssc_only": ("mysql", "ssc"),
}

_PROFILE_SCOPE_LABELS: Mapping[str, str] = {
    "core": "Core Fortify Lab",
    "sast_full": "SAST Full Lab",
    "dast_full": "DAST Full Lab",
    "ssc_only": "SSC Only",
}

_LIFECYCLE_ACTIONS: tuple[LifecycleActionOption, ...] = (
    LifecycleActionOption(
        "start",
        "Start / upgrade",
        "Apply lifecycle adapters in dependency order and verify selected workloads.",
        "retained",
    ),
    LifecycleActionOption(
        "stop",
        "Stop",
        "Scale workloads down in reverse dependency order while preserving persistent data.",
        "retained",
    ),
    LifecycleActionOption(
        "destroy",
        "Destroy (deletes data)",
        "Remove releases/resources; database and LIM destroy paths can delete persistent claims.",
        "deleted",
        destructive=True,
        confirmation_phrase="DESTROY",
    ),
    LifecycleActionOption(
        "restart",
        "Restart",
        "Deferred until Python has an ordered stop/start sequence with health gates.",
        "retained",
        available=False,
        unavailable_reason="Restart needs an ordered stop/start sequence screen before it is safe.",
    ),
    LifecycleActionOption(
        "repair",
        "Repair / retry",
        "Deferred until Python can select and retry a failed lifecycle step with diagnostics context.",
        "retained",
        available=False,
        unavailable_reason="Repair needs failed-step selection and diagnostics context before it is safe.",
    ),
    LifecycleActionOption(
        "reset",
        "Reset scope",
        "Deferred until Python has explicit destructive scope selection.",
        "deleted",
        destructive=True,
        available=False,
        unavailable_reason="Reset needs explicit destructive scope selection before it can execute.",
        confirmation_phrase="DESTROY FORTIFY LAB",
    ),
)

_LIFECYCLE_HANDOFFS: tuple[LifecycleHandoff, ...] = (
    LifecycleHandoff("1", "Logs", "logs", "Review bounded redacted lifecycle and application logs."),
    LifecycleHandoff("2", "Diagnostics", "diagnostics", "Inspect doctor and live status context."),
    LifecycleHandoff("3", "Status", "status", "Refresh the read-only lab status summary."),
    LifecycleHandoff("i", "Inspection", "inspection", "Inspect adapters, command previews, data impact, and ordering."),
    LifecycleHandoff("m", "Main menu", "main", "Return to the main FortifyLab menu."),
)


def lifecycle_action_options() -> tuple[LifecycleActionOption, ...]:
    """Return the Bash-parity lifecycle actions the Python TUI should expose."""

    return _LIFECYCLE_ACTIONS


def lifecycle_completion_handoffs() -> tuple[LifecycleHandoff, ...]:
    """Return post-lifecycle handoffs shared by complete and failure screens."""

    return _LIFECYCLE_HANDOFFS


def build_lifecycle_scope(action_target: str, *, profile_id: str | None = None) -> LifecycleScope:
    """Build a target scope for lifecycle plan previews without executing scripts."""

    if action_target.startswith("app_lifecycle."):
        component_id = action_target.removeprefix("app_lifecycle.")
        return LifecycleScope(component_id, _target_label(component_id), (component_id,), description="Single application lifecycle target.")
    if action_target.startswith("sample_apps."):
        component_id = action_target.removeprefix("sample_apps.")
        return LifecycleScope(component_id, _target_label(component_id), (component_id,), description="Single sample application lifecycle target.")
    if action_target.startswith("lifecycle."):
        if profile_id is not None:
            try:
                component_ids = _PROFILE_SCOPE_COMPONENTS[profile_id]
            except KeyError as exc:
                raise ValueError(f"Unknown lifecycle profile: {profile_id}") from exc
            return LifecycleScope(
                f"profile:{profile_id}",
                f"Selected profile: {_PROFILE_SCOPE_LABELS.get(profile_id, profile_id)}",
                component_ids,
                profile_id=profile_id,
                description="Selected deployment profile workload scope.",
            )
        return LifecycleScope("all", "All lab deployments", _FULL_LAB_COMPONENT_ORDER, description="Full core lab lifecycle scope.")
    raise KeyError(f"Unknown lifecycle action target: {action_target}")


def build_lifecycle_plan(action_target: str, action_id: str, *, profile_id: str | None = None) -> LifecyclePlan:
    """Build a Bash-parity lifecycle plan; this is a dry contract, not execution."""

    scope = build_lifecycle_scope(action_target, profile_id=profile_id)
    action = _find_lifecycle_action(action_id)
    if not action.available:
        raise ValueError(action.unavailable_reason or f"Lifecycle action {action_id} is unavailable")

    component_ids = scope.component_ids
    order_note = "Start runs in dependency order."
    if action.id in {"stop", "destroy"}:
        component_ids = tuple(reversed(component_ids))
        order_note = "Stop and destroy run in reverse dependency order."

    confirmation_phrase = action.confirmation_phrase
    if action.id == "destroy" and scope.id == "all":
        confirmation_phrase = "DESTROY FORTIFY LAB"
    elif action.id == "destroy" and scope.profile_id is not None:
        confirmation_phrase = "DESTROY SELECTED PROFILE"

    steps = tuple(
        LifecyclePlanStep(
            component_id=component_id,
            label=_target_label(component_id),
            operation_id=_operation_id_for(component_id, action.id),
            order=index,
            data_impact=action.data_impact,
        )
        for index, component_id in enumerate(component_ids, start=1)
    )
    for step in steps:
        get_operation(step.operation_id)

    return LifecyclePlan(
        action_id=action.id,
        label=f"{action.label} - {scope.label}",
        scope=scope,
        steps=steps,
        data_impact=action.data_impact,
        destructive=action.destructive,
        confirmation_phrase=confirmation_phrase,
        order_note=order_note,
        handoffs=_LIFECYCLE_HANDOFFS,
    )


def _find_lifecycle_action(action_id: str) -> LifecycleActionOption:
    for action in _LIFECYCLE_ACTIONS:
        if action.id == action_id:
            return action
    raise ValueError(f"Unknown lifecycle action: {action_id}")


def _operation_id_for(component_id: str, action_id: str) -> str:
    if component_id == "scancentral_dast":
        return f"scancentral_dast.{action_id}"
    return f"{component_id}.{action_id}"


def _target_label(component_id: str) -> str:
    return _COMPONENT_TARGETS.get(component_id) or _SAMPLE_TARGETS.get(component_id) or component_id.replace("_", " ").title()


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
    """Lifecycle screen with Bash-style target, action, plan, and confirmation flow."""

    def __init__(
        self,
        action_target: str,
        title: str | None = None,
        *,
        runner: LifecycleRunner | None = None,
    ) -> None:
        self.contract = resolve_lifecycle_action(action_target)
        self.runner = runner or _confirmed_operation_runner
        self.action_options = _screen_action_options(action_target)
        self.selected_action_index = 0
        self.selected_operation_id = self._selected_default_operation_id()
        self.awaiting_confirmation = False
        self.last_preview: DryRunPreviewScreenModel | None = None
        self.last_plan: LifecyclePlan | None = None
        self.last_result: ExecutionResultDisplayModel | None = None
        self.id = f"lifecycle:{action_target}"
        self.title = title or self.contract.label
        self.summary = f"{self.contract.label} lifecycle controls."
        self.lines = ()

    @property
    def selected_action(self) -> LifecycleActionOption | None:
        if not self.action_options:
            return None
        return self.action_options[self.selected_action_index]

    def render(self) -> str:
        lines = [self.summary]
        if not self.contract.supported:
            lines.append(f"Unsupported: {self.contract.unsupported_reason}")
            return "\n".join(lines)

        scope = build_lifecycle_scope(self.contract.action_target)
        lines.append(f"Target: {scope.label}")
        lines.append(scope.description)
        if self.contract.operation_ids:
            lines.append("Catalog operation: " + ", ".join(self.contract.operation_ids))
        lines.append("")
        lines.append("Actions:")
        for index, action in enumerate(self.action_options, start=1):
            marker = ">" if index - 1 == self.selected_action_index else " "
            status = "" if action.available else f" [{action.unavailable_reason}]"
            lines.append(f"{marker} {index}. {action.label} - {action.description}{status}")
        lines.append("")
        lines.append("Use up/down or number to select. Press enter to review the plan. b backs out.")

        action = self.selected_action
        if action is not None and action.available:
            try:
                preview_plan = build_lifecycle_plan(self.contract.action_target, action.id)
            except ValueError:
                preview_plan = None
            if preview_plan is not None:
                lines.append(f"Selected plan: {preview_plan.label}")
                lines.append(f"Order: {preview_plan.order_note}")
                lines.append("Adapter preview: " + ", ".join(preview_plan.operation_ids))

        if self.last_plan is not None:
            lines.append("")
            lines.append("Plan preview")
            lines.append(f"Scope: {self.last_plan.scope.label}")
            lines.append(f"Action: {self.last_plan.label}")
            lines.append(f"Data impact: {self.last_plan.data_impact}")
            lines.append("Steps that will run:")
            for step in self.last_plan.steps:
                lines.append(f"{step.order}. {step.label} -> {step.operation_id}")
            if self.last_plan.destructive:
                lines.append(f"Confirm by typing: {self.last_plan.confirmation_phrase}")
            else:
                lines.append("Continue: press enter to run this lifecycle plan.")
            lines.append("Inspect: press i to review adapters, commands, and handoffs.")
            lines.append("Cancel: press n before execution starts.")

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
            lines.append("")
            lines.append("Handoffs:")
            for handoff in _LIFECYCLE_HANDOFFS:
                lines.append(f"{handoff.key}. {handoff.label} -> {handoff.workflow_target}")
        return "\n".join(line for line in lines if line is not None)

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"back", "b", "escape"}:
            return WorkflowKeyResult("Returned.", exit_screen=True)
        if not self.contract.supported:
            return WorkflowKeyResult(self.contract.unsupported_reason or "Lifecycle action is unsupported.")
        if key in {"up", "down"}:
            self._move_selection(-1 if key == "up" else 1)
            return WorkflowKeyResult(f"Selected {self._selected_operation_label()}.")
        if key in {"1", "2", "3", "4", "5", "6"}:
            index = int(key) - 1
            if index < len(self.action_options):
                self._select_action(index)
                return WorkflowKeyResult(f"Selected {self._selected_operation_label()}.")
        if key in {"p", "d"}:
            self._prepare_plan()
            if self.selected_operation_id is not None:
                self.last_preview = _preview_model(self.contract.action_target, dry_run(self.selected_operation_id))
                return WorkflowKeyResult(f"Previewed {self.last_preview.operation_id}.")
            return WorkflowKeyResult("Prepared lifecycle plan preview.")
        if key in {"c", "enter"}:
            if self.awaiting_confirmation and self.last_plan is not None and not self.last_plan.destructive:
                return self._execute_selected_plan()
            self._prepare_plan()
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
        if key == "y" and self.awaiting_confirmation and self.last_plan is not None:
            if self.last_plan.destructive:
                return WorkflowKeyResult(f"Type {self.last_plan.confirmation_phrase} to confirm destructive lifecycle execution.")
            return self._execute_selected_plan()
        if self.awaiting_confirmation and self.last_plan is not None and key == self.last_plan.confirmation_phrase:
            return self._execute_selected_plan()
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
        if key == "i":
            self._prepare_plan()
            return WorkflowKeyResult("Lifecycle inspection is available in the plan preview.")
        return WorkflowKeyResult(f"No lifecycle action is bound to {key!r}.")

    def _prepare_plan(self) -> None:
        action = self.selected_action
        if action is None:
            raise ValueError("No lifecycle action is selected")
        if not action.available:
            raise ValueError(action.unavailable_reason or f"Lifecycle action {action.id} is unavailable")
        self.last_plan = build_lifecycle_plan(self.contract.action_target, action.id)
        self.selected_operation_id = self.last_plan.operation_ids[0] if self.last_plan.operation_ids else None
        self.last_preview = None
        self.last_result = None

    def _execute_selected_plan(self) -> WorkflowKeyResult:
        if self.last_plan is None:
            self._prepare_plan()
        assert self.last_plan is not None
        self.awaiting_confirmation = False
        results = [_execute_with_runner(self.runner, step.operation_id) for step in self.last_plan.steps]
        failure = next((result for result in results if result.status != "success"), None)
        if failure is not None:
            self.last_result = failure
            return WorkflowKeyResult(failure.message)
        self.last_result = results[-1]
        if len(results) == 1:
            return WorkflowKeyResult(self.last_result.message)
        self.last_result = ExecutionResultDisplayModel(
            status="success",
            operation_id=self.last_plan.operation_ids[-1],
            exit_code=0,
            stdout_summary="",
            stderr_summary="",
            redacted_output=(),
            message="Lifecycle plan completed successfully.",
        )
        return WorkflowKeyResult(self.last_result.message)

    def _select_action(self, index: int) -> None:
        self.selected_action_index = index
        self.selected_operation_id = self._selected_default_operation_id()
        self.awaiting_confirmation = False
        self.last_result = None
        self.last_preview = None
        self.last_plan = None

    def _move_selection(self, delta: int) -> None:
        if not self.action_options:
            return
        self._select_action((self.selected_action_index + delta) % len(self.action_options))

    def _selected_default_operation_id(self) -> str | None:
        action = self.selected_action
        if action is None or not action.available:
            return self.contract.default_operation_id
        try:
            plan = build_lifecycle_plan(self.contract.action_target, action.id)
        except ValueError:
            return self.contract.default_operation_id
        return plan.operation_ids[0] if plan.operation_ids else self.contract.default_operation_id

    def _selected_operation_label(self) -> str:
        action = self.selected_action
        if action is None:
            return "lifecycle action"
        if self.selected_operation_id is not None:
            return self.selected_operation_id
        return action.label


def _screen_action_options(action_target: str) -> tuple[LifecycleActionOption, ...]:
    if action_target == "lifecycle.start_lab":
        return (_find_lifecycle_action("start"),)
    if action_target == "lifecycle.stop_lab":
        return (_find_lifecycle_action("stop"),)
    if action_target == "lifecycle.restart_lab":
        return (_find_lifecycle_action("restart"),)
    if action_target == "lifecycle.reset_lab":
        return (_find_lifecycle_action("destroy"), _find_lifecycle_action("reset"))
    if action_target.startswith(("app_lifecycle.", "sample_apps.")):
        return tuple(_find_lifecycle_action(action_id) for action_id in ("start", "stop", "destroy"))
    return ()


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
