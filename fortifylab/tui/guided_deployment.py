"""Guided deployment workflow contract for the Python TUI.

The workflow is a clone-safe state machine. It previews existing operation
catalog entries, requires explicit confirmation before runner execution, and
uses injected runners in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from fortifylab.diagnostics import redact_diagnostic_text
from fortifylab.operations import OperationRunResult, SensitiveRedactor, dry_run
from fortifylab.operations.catalog import get_operation
from fortifylab.tui.lifecycle import ExecutionResultDisplayModel, build_result_display
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


StageName = Literal["profile_selection", "release_family_selection", "deployment_mode_selection", "plan_preview", "step_controls", "deployment_monitor", "deployment_logs", "deployment_inspection", "completion_handoff"]


class GuidedDeploymentPhase(str, Enum):
    PROFILE = "profile_selection"
    RELEASE_FAMILY = "release_family_selection"
    MODE = "deployment_mode_selection"
    PLAN_PREVIEW = "plan_preview"
    STEPS = "step_controls"
    PREVIEW = "step_controls"
    CONFIRM = "step_controls"
    MONITOR = "deployment_monitor"
    LOGS = "deployment_logs"
    INSPECTION = "deployment_inspection"
    COMPLETE = "completion_handoff"
    CANCELLED = "step_controls"
    BLOCKED = "completion_handoff"


class StepRuntimeState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    PREVIEWED = "PREVIEWED"
    RUNNING = "RUNNING"
    SUCCESS = "COMPLETE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


GuidedStepStatus = StepRuntimeState


class DeploymentStatusColor(str, Enum):
    DIM = "dim"
    CYAN = "cyan"
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    MAGENTA = "magenta"
    GRAY = "gray"


STATUS_COLOR_BY_STATE: dict[StepRuntimeState, DeploymentStatusColor] = {
    StepRuntimeState.PENDING: DeploymentStatusColor.DIM,
    StepRuntimeState.READY: DeploymentStatusColor.GRAY,
    StepRuntimeState.PREVIEWED: DeploymentStatusColor.CYAN,
    StepRuntimeState.RUNNING: DeploymentStatusColor.CYAN,
    StepRuntimeState.SUCCESS: DeploymentStatusColor.GREEN,
    StepRuntimeState.COMPLETE: DeploymentStatusColor.GREEN,
    StepRuntimeState.SKIPPED: DeploymentStatusColor.YELLOW,
    StepRuntimeState.FAILED: DeploymentStatusColor.RED,
    StepRuntimeState.CANCELLED: DeploymentStatusColor.MAGENTA,
    StepRuntimeState.UNAVAILABLE: DeploymentStatusColor.YELLOW,
    StepRuntimeState.UNKNOWN: DeploymentStatusColor.GRAY,
}


@dataclass(frozen=True, init=False)
class GuidedDeploymentProfile:
    id: str
    label: str
    step_ids: tuple[str, ...]
    summary: str
    sample: bool

    def __init__(self, id: str, label: str, step_ids_or_summary, step_ids: tuple[str, ...] | None = None, sample: bool = False) -> None:  # type: ignore[no-untyped-def]
        if step_ids is None:
            resolved_step_ids = tuple(step_ids_or_summary)
            summary = ", ".join(resolved_step_ids)
        else:
            summary = str(step_ids_or_summary)
            resolved_step_ids = tuple(step_ids)
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "step_ids", resolved_step_ids)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "sample", sample)


DeploymentProfile = GuidedDeploymentProfile


@dataclass(frozen=True, init=False)
class GuidedDeploymentMode:
    id: str
    label: str
    summary: str
    available: bool
    unavailable_reason: str | None
    resume_available: bool
    repair_available: bool

    def __init__(
        self,
        id: str,
        label: str,
        summary: str = "",
        *,
        available: bool = True,
        unavailable_reason: str | None = None,
        resume_available: bool = False,
        repair_available: bool = False,
    ) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "summary", summary or label)
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "unavailable_reason", unavailable_reason)
        object.__setattr__(self, "resume_available", resume_available)
        object.__setattr__(self, "repair_available", repair_available)


DeploymentMode = GuidedDeploymentMode


@dataclass(frozen=True)
class ReleaseFamily:
    id: str
    label: str
    summary: str
    flight_plan: str
    version_keys: tuple[str, ...] = (
        "FORTIFY_FLIGHT_PLAN",
        "FORTIFY_SSC_CHART_VERSION",
        "FORTIFY_SSC_IMAGE_TAG",
        "FORTIFY_SCSAST_CHART_VERSION",
        "FORTIFY_SCDAST_CHART_VERSION",
        "FORTIFY_LIM_CHART_VERSION",
    )
    recommended: bool = False


GuidedReleaseFamily = ReleaseFamily


@dataclass(frozen=True, init=False)
class GuidedDeploymentStep:
    id: str
    label: str
    operation_id: str | None
    state: StepRuntimeState
    summary: str
    required: bool
    available: bool
    unavailable_reason: str | None

    def __init__(
        self,
        id: str,
        label: str,
        operation_id: str | None,
        state_or_summary: StepRuntimeState | str = StepRuntimeState.READY,
        *,
        why: str | None = None,
        required: bool = True,
        available: bool | None = None,
        unavailable_reason: str | None = None,
    ) -> None:
        if isinstance(state_or_summary, StepRuntimeState):
            state = state_or_summary
            summary = why or "ready for preview"
        elif str(state_or_summary) in StepRuntimeState.__members__:
            state = StepRuntimeState[str(state_or_summary)]
            summary = why or "ready for preview"
        else:
            summary = str(state_or_summary)
            state = StepRuntimeState.READY
        resolved_available = state is not StepRuntimeState.UNAVAILABLE if available is None else available
        canonical = {
            "postgresql": "PostgreSQL",
            "ssc": "SSC",
            "scancentral_sast": "ScanCentral SAST",
            "scancentral_dast": "ScanCentral DAST",
            "juice_shop": "Juice Shop",
            "webgoat": "WebGoat",
            "dvwa": "DVWA",
        }
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "label", canonical.get(id, label))
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "required", required)
        object.__setattr__(self, "available", resolved_available)
        object.__setattr__(self, "unavailable_reason", unavailable_reason or (summary if state is StepRuntimeState.UNAVAILABLE else None))

    @property
    def step_id(self) -> str:
        return self.id

    @property
    def why(self) -> str:
        return self.unavailable_reason or self.summary


@dataclass(frozen=True)
class StepPreview:
    step_id: str
    operation_id: str | None
    commands: tuple[str, ...]
    confirmation_required: bool
    confirmation_prompt: str | None
    message: str


@dataclass(frozen=True)
class StepResult:
    step_id: str
    status: StepRuntimeState
    operation_id: str | None
    display: ExecutionResultDisplayModel | None
    message: str


@dataclass(frozen=True)
class CompletionHandoff:
    key: str
    label: str
    workflow_target: str
    summary: str


@dataclass(frozen=True)
class DeploymentPlanStep:
    step_id: str
    label: str
    operation_id: str | None
    commands: tuple[str, ...]
    required: bool
    adapter_id: str | None
    config_keys: tuple[str, ...]
    confirmation_required: bool
    summary: str


@dataclass(frozen=True)
class DeploymentPlan:
    profile: GuidedDeploymentProfile
    release_family: ReleaseFamily
    mode: GuidedDeploymentMode
    steps: tuple[DeploymentPlanStep, ...]
    continue_prompt: str = "Continue with deployment? If you proceed, FortifyLab will automatically run the planned deployment steps."
    confirmation_phrase: str = "DEPLOY"
    mutating: bool = True
    stop_on_failure: bool = True

    @property
    def operation_ids(self) -> tuple[str, ...]:
        return tuple(step.operation_id for step in self.steps if step.operation_id is not None)

    @property
    def command_count(self) -> int:
        return sum(len(step.commands) for step in self.steps)


@dataclass(frozen=True)
class DeploymentStatusRow:
    component: str
    operation: str
    state: StepRuntimeState
    duration: str = "--"
    last_update: str = ""

    @property
    def color(self) -> DeploymentStatusColor:
        return STATUS_COLOR_BY_STATE.get(self.state, DeploymentStatusColor.GRAY)


@dataclass(frozen=True)
class DeploymentLogEvent:
    step_id: str
    stream: Literal["stdout", "stderr", "system"]
    message: str


@dataclass(frozen=True)
class DeploymentLogBuffer:
    events: tuple[DeploymentLogEvent, ...] = ()
    limit: int = 200

    def append(self, event: DeploymentLogEvent) -> "DeploymentLogBuffer":
        redacted = DeploymentLogEvent(event.step_id, event.stream, redact_diagnostic_text(event.message))
        return DeploymentLogBuffer((*self.events, redacted)[-self.limit :], self.limit)

    def render(self) -> tuple[str, ...]:
        return tuple(f"{event.step_id} {event.stream}: {event.message}" for event in self.events)


@dataclass(frozen=True)
class DeploymentInspection:
    profile_id: str
    release_family_id: str
    mode_id: str
    current_step_id: str | None
    adapter_id: str | None
    command_preview: tuple[str, ...]
    config_keys: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuidedDeploymentRunContract:
    plan: DeploymentPlan
    status_rows: tuple[DeploymentStatusRow, ...]
    logs: DeploymentLogBuffer = field(default_factory=DeploymentLogBuffer)
    inspection: DeploymentInspection | None = None
    awaiting_deploy_confirmation: bool = False

    @property
    def confirmation_note(self) -> str:
        return f"Type {self.plan.confirmation_phrase} to auto-run the planned deployment steps."


@dataclass(frozen=True)
class GuidedDeploymentSnapshot:
    phase: GuidedDeploymentPhase
    profile: GuidedDeploymentProfile
    mode: GuidedDeploymentMode
    steps: tuple[GuidedDeploymentStep, ...]
    current_step_index: int
    step_statuses: tuple[StepRuntimeState, ...]
    preview: StepPreview | None = None
    last_result: StepResult | None = None
    awaiting_confirmation: bool = False
    message: str = ""

    @property
    def current_step(self) -> GuidedDeploymentStep:
        return self.steps[self.current_step_index]

    @property
    def complete(self) -> bool:
        actionable = [status for step, status in zip(self.steps, self.step_statuses, strict=True) if step.required and step.available]
        return bool(actionable) and all(status is StepRuntimeState.COMPLETE for status in actionable)


GuidedDeploymentRunner = Callable[[str], OperationRunResult]
StepsProvider = Callable[[str, str], tuple[GuidedDeploymentStep, ...]]


DEPLOYMENT_STEPS: tuple[GuidedDeploymentStep, ...] = (
    GuidedDeploymentStep("mysql", "MySQL", "mysql.start", "Database dependency for SSC and sample workflows."),
    GuidedDeploymentStep("postgresql", "PostgreSQL", "postgresql.start", "Database dependency for selected Fortify services."),
    GuidedDeploymentStep("ssc", "SSC", "ssc.start", "Core Fortify application security management service."),
    GuidedDeploymentStep("lim", "LIM", "lim.start", "License and infrastructure management service."),
    GuidedDeploymentStep("scancentral_sast", "ScanCentral SAST", "scancentral_sast.start", "SAST controller and sensor deployment."),
    GuidedDeploymentStep("scancentral_dast", "ScanCentral DAST", "scancentral_dast.start", "DAST core and scanner deployment."),
    GuidedDeploymentStep("juice_shop", "Juice Shop", "juice_shop.start", "Optional sample app used by the first-scan demo.", required=False),
    GuidedDeploymentStep("webgoat", "WebGoat", "webgoat.start", "Optional sample app for training and validation.", required=False),
    GuidedDeploymentStep("dvwa", "DVWA", "dvwa.start", "Optional sample app for training and validation.", required=False),
)


DEPLOYMENT_PROFILES: tuple[GuidedDeploymentProfile, ...] = (
    GuidedDeploymentProfile("core", "Core Fortify Lab", "SSC, LIM, databases, ScanCentral SAST, and ScanCentral DAST.", ("mysql", "postgresql", "ssc", "lim", "scancentral_sast", "scancentral_dast")),
    GuidedDeploymentProfile("sast_full", "SAST Full Lab", "Core SAST services with Juice Shop for the first-scan path.", ("mysql", "postgresql", "ssc", "lim", "scancentral_sast", "juice_shop"), sample=True),
    GuidedDeploymentProfile("dast_full", "DAST Full Lab", "Core DAST services with sample targets.", ("mysql", "postgresql", "ssc", "lim", "scancentral_dast", "juice_shop", "webgoat", "dvwa"), sample=True),
)


DEPLOYMENT_MODES: tuple[GuidedDeploymentMode, ...] = (
    GuidedDeploymentMode("fresh", "Fresh deployment", "Run selected profile steps from the beginning."),
    GuidedDeploymentMode("resume", "Resume deployment", "Represent resume state and continue from the selected step.", resume_available=True),
    GuidedDeploymentMode("repair", "Repair deployment", "Represent repair intent for failed or unavailable steps.", repair_available=True),
    GuidedDeploymentMode("component", "Component deployment", "Run one selected component through the same preview and confirmation contract."),
)


COMPLETION_HANDOFFS: tuple[CompletionHandoff, ...] = (
    CompletionHandoff("1", "Diagnostics", "diagnostics", "Review doctor and status context after deployment."),
    CompletionHandoff("2", "Status", "status", "Inspect the current lab status summary."),
    CompletionHandoff("3", "Logs", "logs", "Inspect redacted wizard and application log sources."),
    CompletionHandoff("4", "Help", "help_center", "Read guided deployment and troubleshooting guidance."),
    CompletionHandoff("5", "Lifecycle", "lifecycle", "Start, stop, or destroy supported components after deployment."),
)


RELEASE_FAMILIES: tuple[ReleaseFamily, ...] = (
    ReleaseFamily("current", "Current recommended", "Use the repository's recommended Fortify chart and image family.", "recommended", recommended=True),
    ReleaseFamily("stable", "Stable pinned", "Use a pinned stable family for repeatable lab rebuilds.", "stable"),
    ReleaseFamily("legacy", "Legacy compatibility", "Use older compatible values when validating upgrade or repair behavior.", "legacy"),
)


STEP_CONFIG_KEYS: dict[str, tuple[str, ...]] = {
    "mysql": ("FORTIFY_MYSQL_CHART_VERSION", "FORTIFY_MYSQL_IMAGE_TAG"),
    "postgresql": ("FORTIFY_POSTGRES_CHART_VERSION", "FORTIFY_POSTGRES_IMAGE_TAG"),
    "ssc": ("FORTIFY_SSC_CHART_VERSION", "FORTIFY_SSC_IMAGE_TAG", "SSC_URL", "DEFAULT_ALIAS"),
    "lim": ("FORTIFY_LIM_CHART_VERSION", "LIM_URL", "LIM_API_URL", "LIM_POOL_NAME"),
    "scancentral_sast": ("FORTIFY_SCSAST_CHART_VERSION", "FORTIFY_SCSAST_CTRL_IMAGE_TAG", "FORTIFY_SCSAST_WORKER_IMAGE_TAG", "SCSAST_URL"),
    "scancentral_dast": ("FORTIFY_SCDAST_CHART_VERSION", "SCDAST_URL", "SCDAST_SSC_USER"),
    "juice_shop": ("JUICE_SHOP_URL",),
    "webgoat": ("WEBGOAT_URL",),
    "dvwa": ("DVWA_URL",),
}


def deployment_profile(profile_id: str, *, profiles: tuple[GuidedDeploymentProfile, ...] = DEPLOYMENT_PROFILES) -> GuidedDeploymentProfile:
    for profile in profiles:
        if profile.id == profile_id:
            return profile
    raise KeyError(f"Unknown deployment profile: {profile_id}")


def deployment_mode(mode_id: str, *, modes: tuple[GuidedDeploymentMode, ...] = DEPLOYMENT_MODES) -> GuidedDeploymentMode:
    for mode in modes:
        if mode.id == mode_id:
            return mode
    raise KeyError(f"Unknown deployment mode: {mode_id}")


def release_family(family_id: str, *, families: tuple[ReleaseFamily, ...] = RELEASE_FAMILIES) -> ReleaseFamily:
    for family in families:
        if family.id == family_id:
            return family
    raise KeyError(f"Unknown release family: {family_id}")


def build_deployment_plan(
    *,
    profile_id: str = "core",
    release_family_id: str = "current",
    mode_id: str = "fresh",
    profiles: tuple[GuidedDeploymentProfile, ...] = DEPLOYMENT_PROFILES,
    families: tuple[ReleaseFamily, ...] = RELEASE_FAMILIES,
    modes: tuple[GuidedDeploymentMode, ...] = DEPLOYMENT_MODES,
    steps_provider: StepsProvider | None = None,
) -> DeploymentPlan:
    profile = deployment_profile(profile_id, profiles=profiles)
    family = release_family(release_family_id, families=families)
    mode = deployment_mode(mode_id, modes=modes)
    provider = steps_provider or _default_steps_for_profile
    steps = tuple(_plan_step(step) for step in provider(profile.id, mode.id))
    return DeploymentPlan(profile, family, mode, steps)


def build_deployment_status_rows(plan: DeploymentPlan) -> tuple[DeploymentStatusRow, ...]:
    return tuple(
        DeploymentStatusRow(
            component=step.label,
            operation=step.operation_id or "unavailable",
            state=StepRuntimeState.PENDING if step.operation_id else StepRuntimeState.UNAVAILABLE,
            last_update="queued" if step.operation_id else "operation adapter unavailable",
        )
        for step in plan.steps
    )


def build_deployment_inspection(plan: DeploymentPlan, *, current_step_id: str | None = None) -> DeploymentInspection:
    selected = _find_plan_step(plan, current_step_id) if current_step_id else (plan.steps[0] if plan.steps else None)
    return DeploymentInspection(
        profile_id=plan.profile.id,
        release_family_id=plan.release_family.id,
        mode_id=plan.mode.id,
        current_step_id=selected.step_id if selected else None,
        adapter_id=selected.adapter_id if selected else None,
        command_preview=selected.commands if selected else (),
        config_keys=tuple(dict.fromkeys((*plan.release_family.version_keys, *(selected.config_keys if selected else ())))),
        notes=(
            "Clone-safe inspection only; no Kubernetes, Helm, Docker, network, scripts, or credentials are invoked.",
            "Real execution wiring must use injected runners and preserve the DEPLOY confirmation gate.",
        ),
    )


def build_guided_run_contract(plan: DeploymentPlan, *, current_step_id: str | None = None, log_limit: int = 200) -> GuidedDeploymentRunContract:
    return GuidedDeploymentRunContract(
        plan=plan,
        status_rows=build_deployment_status_rows(plan),
        logs=DeploymentLogBuffer(limit=log_limit),
        inspection=build_deployment_inspection(plan, current_step_id=current_step_id),
        awaiting_deploy_confirmation=True,
    )


def _plan_step(step: GuidedDeploymentStep) -> DeploymentPlanStep:
    commands: tuple[str, ...] = ()
    confirmation_required = False
    summary = step.summary
    if step.operation_id is not None and step.available and step.state is not StepRuntimeState.UNAVAILABLE:
        operation = get_operation(step.operation_id)
        preview = dry_run(operation.id)
        commands = preview.commands
        confirmation_required = preview.confirmation_required
        summary = operation.description or step.summary
    return DeploymentPlanStep(
        step_id=step.id,
        label=_display_label(step),
        operation_id=step.operation_id,
        commands=commands,
        required=step.required,
        adapter_id=step.operation_id,
        config_keys=STEP_CONFIG_KEYS.get(step.id, ()),
        confirmation_required=confirmation_required,
        summary=summary,
    )


def _find_plan_step(plan: DeploymentPlan, step_id: str | None) -> DeploymentPlanStep:
    for step in plan.steps:
        if step.step_id == step_id:
            return step
    raise KeyError(f"Unknown deployment plan step: {step_id}")


def deployment_steps_for_profile(profile_id: str) -> tuple[GuidedDeploymentStep, ...]:
    profile = deployment_profile(profile_id)
    return _default_steps_for_profile(profile.id, "fresh")


def build_guided_deployment_snapshot(
    *,
    profile_id: str = "core",
    mode_id: str = "fresh",
    current_step_index: int = 0,
) -> GuidedDeploymentSnapshot:
    profile = deployment_profile(profile_id)
    mode = deployment_mode(mode_id)
    steps = deployment_steps_for_profile(profile.id)
    return _snapshot(profile, mode, steps, current_step_index, GuidedDeploymentPhase.PROFILE, "Select a deployment profile.")


class GuidedDeploymentScreen(WorkflowScreen):
    """Pure guided deployment state machine with fake-runner compatible hooks."""

    def __init__(
        self,
        *,
        profiles: tuple[GuidedDeploymentProfile, ...] = DEPLOYMENT_PROFILES,
        modes: tuple[GuidedDeploymentMode, ...] = DEPLOYMENT_MODES,
        steps_provider: StepsProvider | None = None,
        profile_id: str | None = None,
        mode_id: str = "fresh",
        runner: GuidedDeploymentRunner | None = None,
    ) -> None:
        super().__init__(
            "guided_deployment",
            "Guided deployment",
            "Guided deployment contract: Profile selection, deployment mode selection, step preview, confirmation, cancel, and completion handoffs.",
        )
        self.profiles = profiles
        self.modes = modes
        self.steps_provider = steps_provider or _default_steps_for_profile
        self.runner = runner or _blocked_guided_runner
        self.selected_profile_index = _index(profile_id or profiles[0].id, profiles)
        self.selected_mode_index = _index(mode_id, modes)
        self.selected_handoff_index = 0
        profile = profiles[self.selected_profile_index]
        mode = modes[self.selected_mode_index]
        self.snapshot = _snapshot(profile, mode, self.steps_provider(profile.id, mode.id), 0, GuidedDeploymentPhase.PROFILE, "Select a deployment profile.")
        self.last_preview: StepPreview | None = None
        self.last_result: StepResult | None = None

    @property
    def stage(self) -> StageName:
        return self.snapshot.phase.value  # type: ignore[return-value]

    @property
    def selected_profile_id(self) -> str:
        return self.snapshot.profile.id

    @property
    def selected_mode_id(self) -> str:
        return self.snapshot.mode.id

    @property
    def selected_step_id(self) -> str:
        return self.snapshot.current_step.id

    def step_state(self, step_id: str) -> StepRuntimeState:
        for step, status in zip(self.snapshot.steps, self.snapshot.step_statuses, strict=True):
            if step.id == step_id:
                return status
        raise KeyError(f"Unknown guided deployment step: {step_id}")

    def mark_all_steps_complete(self) -> None:
        self.snapshot = _replace_snapshot(
            self.snapshot,
            phase=GuidedDeploymentPhase.COMPLETE,
            step_statuses=tuple(StepRuntimeState.COMPLETE for _step in self.snapshot.steps),
            message="Guided deployment complete.",
        )

    def render(self) -> str:
        lines = [
            self.summary,
            f"Stage: {self.stage}",
            f"Profile: {self.snapshot.profile.label}",
            f"Mode: {self.snapshot.mode.label}",
            f"Message: {self.snapshot.message}",
            "",
        ]
        if self.snapshot.phase is GuidedDeploymentPhase.PROFILE:
            lines.append("Profile selection:")
            for index, profile in enumerate(self.profiles, start=1):
                marker = ">" if index - 1 == self.selected_profile_index else " "
                lines.append(f"{marker} {index}. {profile.label} - {profile.summary}")
        elif self.snapshot.phase is GuidedDeploymentPhase.MODE:
            lines.append("Deployment mode selection:")
            for index, mode in enumerate(self.modes, start=1):
                marker = ">" if index - 1 == self.selected_mode_index else " "
                lines.append(f"{marker} {index}. {mode.label} - {mode.summary}")
        elif self.snapshot.phase is GuidedDeploymentPhase.COMPLETE:
            lines.append("Completion handoffs:")
            for index, handoff in enumerate(COMPLETION_HANDOFFS):
                marker = ">" if index == self.selected_handoff_index else " "
                lines.append(f"{marker} {handoff.key}  {handoff.label} -> {handoff.workflow_target}: {handoff.summary}")
        else:
            lines.append("Step controls:")
            for index, (step, status) in enumerate(zip(self.snapshot.steps, self.snapshot.step_statuses, strict=True), start=1):
                marker = ">" if index - 1 == self.snapshot.current_step_index else " "
                detail = f" - {step.why}" if step.why else ""
                lines.append(f"{marker} {index}. {status.value} {_display_label(step)} -> {step.operation_id or 'unavailable'}{detail}")
        if self.last_preview is not None:
            lines.extend(("", f"Preview: {self.last_preview.message}"))
            lines.extend(f"  {command}" for command in self.last_preview.commands)
            if self.last_preview.confirmation_prompt:
                lines.append(f"Confirm: {self.last_preview.confirmation_prompt}")
        if self.last_result is not None:
            lines.extend(("", f"Result: {self.last_result.message}"))
            if self.last_result.display is not None:
                lines.extend(self.last_result.display.redacted_output)
        lines.extend(("", "Actions:", "up/down  Select", "number  Jump", "enter/c  Confirm", "p/v  Preview", "y  Run confirmed", "n  Cancel", "m  Mode selection", "s  Step controls", "r  Refresh", "b  Back", "q  Quit"))
        return redact_diagnostic_text("\n".join(lines))

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"back", "b", "escape", "", "q"}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        if key in {"r", "refresh"}:
            return WorkflowKeyResult("Refreshed guided deployment workflow.")
        if key == "m":
            self.snapshot = _replace_snapshot(self.snapshot, phase=GuidedDeploymentPhase.MODE, message="Select a deployment mode.")
            return WorkflowKeyResult("Deployment mode selection.")
        if key == "s":
            self.snapshot = _replace_snapshot(self.snapshot, phase=GuidedDeploymentPhase.STEPS, message="Select a deployment step.")
            return WorkflowKeyResult("Per-step controls.")
        if key in {"up", "k", "down", "j"}:
            return self._move(-1 if key in {"up", "k"} else 1)
        if key.isdigit():
            return self._select_number(key)
        if key in {"p", "v"}:
            return self.preview_step()
        if key == "enter":
            if self.snapshot.phase is GuidedDeploymentPhase.PROFILE:
                self.snapshot = _replace_snapshot(self.snapshot, phase=GuidedDeploymentPhase.MODE, message=f"Selected {self.snapshot.profile.label} profile.")
                return WorkflowKeyResult(self.snapshot.message)
            if self.snapshot.phase is GuidedDeploymentPhase.MODE:
                self.snapshot = _replace_snapshot(self.snapshot, phase=GuidedDeploymentPhase.STEPS, message=f"Selected {self.snapshot.mode.label} mode.")
                return WorkflowKeyResult(self.snapshot.message)
            return self.confirm_step()
        if key == "c":
            return self.confirm_step()
        if key == "y":
            return self.run_confirmed_step()
        if key in {"n", "cancel"}:
            return self.cancel_step()
        if key == "o":
            return self.open_selected_handoff()
        return WorkflowKeyResult(f"No guided deployment workflow action is bound to {key!r}.")

    on_key = handle_key

    def preview_step(self) -> WorkflowKeyResult:
        step = self.snapshot.current_step
        if self.step_state(step.id) is StepRuntimeState.UNAVAILABLE or not step.available:
            return WorkflowKeyResult(f"{_display_label(step)} is unavailable: {step.why}")
        preview = build_step_preview(step)
        self.last_preview = preview
        self.snapshot = _replace_step_status(self.snapshot, self.snapshot.current_step_index, StepRuntimeState.PREVIEWED, phase=GuidedDeploymentPhase.PREVIEW, preview=preview, awaiting_confirmation=False, message=preview.message)
        return WorkflowKeyResult(preview.message)

    def confirm_step(self) -> WorkflowKeyResult:
        step = self.snapshot.current_step
        if self.step_state(step.id) is StepRuntimeState.UNAVAILABLE or not step.available:
            return WorkflowKeyResult(f"{_display_label(step)} is unavailable: {step.why}")
        preview = self.last_preview or build_step_preview(step)
        self.last_preview = preview
        self.snapshot = _replace_step_status(self.snapshot, self.snapshot.current_step_index, StepRuntimeState.PREVIEWED, phase=GuidedDeploymentPhase.CONFIRM, preview=preview, awaiting_confirmation=True, message="Confirmation required before guided deployment execution.")
        return WorkflowKeyResult(self.snapshot.message)

    def run_confirmed_step(self) -> WorkflowKeyResult:
        step = self.snapshot.current_step
        if self.step_state(step.id) is StepRuntimeState.UNAVAILABLE or not step.available:
            return WorkflowKeyResult(f"{_display_label(step)} is unavailable: {step.why}")
        if not self.snapshot.awaiting_confirmation:
            return WorkflowKeyResult("Guided deployment execution requires preview and confirmation first.")
        result = _execute_guided_step(step, self.runner)
        self.last_result = result
        phase = GuidedDeploymentPhase.COMPLETE if result.status is StepRuntimeState.COMPLETE and _would_complete(self.snapshot) else GuidedDeploymentPhase.STEPS
        self.snapshot = _replace_step_status(self.snapshot, self.snapshot.current_step_index, result.status, phase=phase, last_result=result, awaiting_confirmation=False, message=result.message)
        return WorkflowKeyResult(result.message)

    def cancel_step(self) -> WorkflowKeyResult:
        self.snapshot = _replace_step_status(self.snapshot, self.snapshot.current_step_index, StepRuntimeState.CANCELLED, phase=GuidedDeploymentPhase.CANCELLED, awaiting_confirmation=False, message="Guided deployment step cancelled.")
        return WorkflowKeyResult(self.snapshot.message)

    def open_selected_handoff(self) -> WorkflowKeyResult:
        if self.snapshot.phase not in {GuidedDeploymentPhase.COMPLETE, GuidedDeploymentPhase.BLOCKED}:
            return WorkflowKeyResult("Completion handoffs are available after guided deployment completes or blocks.")
        handoff = COMPLETION_HANDOFFS[self.selected_handoff_index]
        return WorkflowKeyResult(f"Open workflow target: {handoff.workflow_target}.", open_target=handoff.workflow_target)

    def _move(self, offset: int) -> WorkflowKeyResult:
        if self.snapshot.phase is GuidedDeploymentPhase.PROFILE:
            self.selected_profile_index = (self.selected_profile_index + offset) % len(self.profiles)
            return self._select_profile(self.selected_profile_index)
        if self.snapshot.phase is GuidedDeploymentPhase.MODE:
            self.selected_mode_index = (self.selected_mode_index + offset) % len(self.modes)
            return self._select_mode(self.selected_mode_index)
        if self.snapshot.phase is GuidedDeploymentPhase.COMPLETE:
            self.selected_handoff_index = (self.selected_handoff_index + offset) % len(COMPLETION_HANDOFFS)
            return WorkflowKeyResult(f"Selected handoff: {COMPLETION_HANDOFFS[self.selected_handoff_index].label}.")
        index = (self.snapshot.current_step_index + offset) % len(self.snapshot.steps)
        self.snapshot = _replace_snapshot(self.snapshot, current_step_index=index, phase=GuidedDeploymentPhase.STEPS, message=f"Selected step {_display_label(self.snapshot.steps[index])}.")
        return WorkflowKeyResult(self.snapshot.message)

    def _select_number(self, key: str) -> WorkflowKeyResult:
        index = int(key) - 1
        if self.snapshot.phase is GuidedDeploymentPhase.PROFILE and 0 <= index < len(self.profiles):
            return self._select_profile(index)
        if self.snapshot.phase is GuidedDeploymentPhase.MODE and 0 <= index < len(self.modes):
            return self._select_mode(index)
        if self.snapshot.phase is GuidedDeploymentPhase.COMPLETE and 0 <= index < len(COMPLETION_HANDOFFS):
            self.selected_handoff_index = index
            return self.open_selected_handoff()
        if 0 <= index < len(self.snapshot.steps):
            self.snapshot = _replace_snapshot(self.snapshot, current_step_index=index, phase=GuidedDeploymentPhase.STEPS, message=f"Selected step {_display_label(self.snapshot.steps[index])}.")
            return WorkflowKeyResult(self.snapshot.message)
        return WorkflowKeyResult(f"No guided deployment selection is bound to {key!r}.")

    def _select_profile(self, index: int) -> WorkflowKeyResult:
        profile = self.profiles[index]
        self.selected_profile_index = index
        mode = self.snapshot.mode
        self.snapshot = _snapshot(profile, mode, self.steps_provider(profile.id, mode.id), 0, GuidedDeploymentPhase.PROFILE, f"Selected profile {profile.label}.")
        return WorkflowKeyResult(self.snapshot.message)

    def _select_mode(self, index: int) -> WorkflowKeyResult:
        mode = self.modes[index]
        self.selected_mode_index = index
        profile = self.snapshot.profile
        steps = self.steps_provider(profile.id, mode.id)
        message = f"Selected mode {mode.label}."
        self.snapshot = _snapshot(profile, mode, steps, 0, GuidedDeploymentPhase.MODE, message)
        return WorkflowKeyResult(message)


def build_guided_deployment_workflow(**kwargs) -> GuidedDeploymentScreen:  # type: ignore[no-untyped-def]
    return GuidedDeploymentScreen(**kwargs)


def build_step_preview(step: GuidedDeploymentStep) -> StepPreview:
    if not step.available or step.operation_id is None or step.state is StepRuntimeState.UNAVAILABLE:
        return StepPreview(step.id, step.operation_id, (), False, None, step.unavailable_reason or f"{step.label} is unavailable.")
    preview = dry_run(step.operation_id)
    return StepPreview(step.id, preview.operation_id, preview.commands, preview.confirmation_required, preview.confirmation_prompt, f"Previewed {preview.operation_id} guided deployment step: {step.label}.")


def _execute_guided_step(step: GuidedDeploymentStep, runner: GuidedDeploymentRunner) -> StepResult:
    redactor = SensitiveRedactor()
    if not step.available or step.operation_id is None:
        return StepResult(step.id, StepRuntimeState.UNAVAILABLE, step.operation_id, None, step.unavailable_reason or f"{step.label} is unavailable.")
    try:
        display = build_result_display(runner(step.operation_id))
    except Exception as exc:  # pragma: no cover - runner failures are displayed, not re-raised.
        return StepResult(step.id, StepRuntimeState.FAILED, step.operation_id, None, redactor.text(str(exc)))
    status = StepRuntimeState.COMPLETE if display.status == "success" else StepRuntimeState.FAILED
    return StepResult(step.id, status, step.operation_id, display, redactor.text(display.message))


def _blocked_guided_runner(operation_id: str) -> OperationRunResult:
    raise RuntimeError(f"No guided deployment runner is configured for {operation_id}.")


def _default_steps_for_profile(profile_id: str, mode_id: str) -> tuple[GuidedDeploymentStep, ...]:
    profile = deployment_profile(profile_id)
    by_id = {step.id: step for step in DEPLOYMENT_STEPS}
    state = StepRuntimeState.READY if mode_id == "fresh" else StepRuntimeState.UNAVAILABLE
    reason = "ready for preview" if mode_id == "fresh" else "live resume/repair discovery is unavailable in clone-safe contract mode"
    return tuple(_step_with_state(by_id[step_id], state, reason) for step_id in profile.step_ids)


def _step_with_state(step: GuidedDeploymentStep, state: StepRuntimeState, summary: str) -> GuidedDeploymentStep:
    return GuidedDeploymentStep(step.id, step.label, step.operation_id, state, why=summary, required=step.required, available=state is not StepRuntimeState.UNAVAILABLE)


def _snapshot(
    profile: GuidedDeploymentProfile,
    mode: GuidedDeploymentMode,
    steps: tuple[GuidedDeploymentStep, ...],
    current_step_index: int,
    phase: GuidedDeploymentPhase,
    message: str,
) -> GuidedDeploymentSnapshot:
    bounded_index = min(max(current_step_index, 0), max(len(steps) - 1, 0))
    statuses = tuple(step.state if index == bounded_index else StepRuntimeState.PENDING for index, step in enumerate(steps))
    return GuidedDeploymentSnapshot(phase, profile, mode, steps, bounded_index, statuses, message=message)


def _replace_step_status(
    snapshot: GuidedDeploymentSnapshot,
    index: int,
    status: StepRuntimeState,
    *,
    phase: GuidedDeploymentPhase,
    preview: StepPreview | None = None,
    last_result: StepResult | None = None,
    awaiting_confirmation: bool = False,
    message: str,
) -> GuidedDeploymentSnapshot:
    statuses = list(snapshot.step_statuses)
    statuses[index] = status
    return _replace_snapshot(snapshot, phase=phase, step_statuses=tuple(statuses), preview=preview, last_result=last_result, awaiting_confirmation=awaiting_confirmation, message=message)


def _replace_snapshot(snapshot: GuidedDeploymentSnapshot, **changes) -> GuidedDeploymentSnapshot:  # type: ignore[no-untyped-def]
    values = {
        "phase": snapshot.phase,
        "profile": snapshot.profile,
        "mode": snapshot.mode,
        "steps": snapshot.steps,
        "current_step_index": snapshot.current_step_index,
        "step_statuses": snapshot.step_statuses,
        "preview": snapshot.preview,
        "last_result": snapshot.last_result,
        "awaiting_confirmation": snapshot.awaiting_confirmation,
        "message": snapshot.message,
    }
    values.update(changes)
    return GuidedDeploymentSnapshot(**values)


def _would_complete(snapshot: GuidedDeploymentSnapshot) -> bool:
    statuses = list(snapshot.step_statuses)
    statuses[snapshot.current_step_index] = StepRuntimeState.COMPLETE
    candidate = _replace_snapshot(snapshot, step_statuses=tuple(statuses))
    return candidate.complete


def _canonical_step_label(step_id: str, label: str) -> str:
    canonical = {
        "postgresql": "PostgreSQL",
        "ssc": "SSC",
        "scancentral_sast": "ScanCentral SAST",
        "scancentral_dast": "ScanCentral DAST",
        "juice_shop": "Juice Shop",
        "webgoat": "WebGoat",
        "dvwa": "DVWA",
    }
    return canonical.get(step_id, label)


def _display_label(step: GuidedDeploymentStep) -> str:
    labels = {"mysql": "MySQL", "postgresql": "PostgreSQL", "ssc": "SSC"}
    return labels.get(step.id, step.label)


def _index(item_id: str, items) -> int:  # type: ignore[no-untyped-def]
    ids = tuple(item.id for item in items)
    return ids.index(item_id)
