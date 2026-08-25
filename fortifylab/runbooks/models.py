"""Python-native runbook and help contracts for M6."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import os
import re
import shlex
import subprocess
import time


class RunbookRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


class RunbookSource(str, Enum):
    OFFICIAL = "Official"
    TRAINING = "Training"
    LOCAL = "Local"
    CUSTOM = "Custom"


class RunbookExecutionScope(str, Enum):
    CLONE_SAFE = "clone-safe"
    ENVIRONMENT_DEPENDENT = "environment-dependent"


class RunbookAction(str, Enum):
    VALIDATE = "validate"
    PREVIEW_SCRIPT = "preview-script"
    PREVIEW_COMMAND = "preview-command"
    RUN = "run"


class RequirementStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    NOT_CHECKED = "not-checked"


@dataclass(frozen=True)
class RunbookParameter:
    name: str
    description: str = ""
    default: str = ""
    default_from_env: str = ""
    required: bool = False

    @property
    def env_name(self) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", self.name.upper())

    @property
    def secret(self) -> bool:
        return bool(re.search(r"(pass|password|token|secret|key|credential)", self.name, re.IGNORECASE))


@dataclass(frozen=True)
class RunbookMetadata:
    id: str
    name: str
    description: str
    path: Path
    source: RunbookSource
    domain: str = "General"
    category: str = "General"
    risk: RunbookRisk = RunbookRisk.LOW
    order: int = 1000
    requires: tuple[str, ...] = ()
    type: str = "script"
    parameters: tuple[RunbookParameter, ...] = field(default_factory=tuple)

    @property
    def clone_safe_actions(self) -> tuple[RunbookAction, ...]:
        return (RunbookAction.VALIDATE, RunbookAction.PREVIEW_SCRIPT, RunbookAction.PREVIEW_COMMAND)

    @property
    def environment_dependent_actions(self) -> tuple[RunbookAction, ...]:
        return (RunbookAction.RUN,)


@dataclass(frozen=True)
class HelpTopic:
    id: str
    label: str
    offline_path: Path
    online_route: str
    scope: RunbookExecutionScope = RunbookExecutionScope.CLONE_SAFE


@dataclass(frozen=True, init=False)
class RequirementCheck:
    name: str
    description: str
    scope: RunbookExecutionScope
    available: bool | None
    detail: str

    def __init__(
        self,
        name: str | None = None,
        *,
        tool: str | None = None,
        description: str = "",
        scope: RunbookExecutionScope = RunbookExecutionScope.ENVIRONMENT_DEPENDENT,
        available: bool | None = None,
        detail: str = "",
    ) -> None:
        object.__setattr__(self, "name", name or tool or "")
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "detail", detail)

    @property
    def tool(self) -> str:
        return self.name


@dataclass(frozen=True)
class RequirementResult:
    requirement: RequirementCheck
    status: RequirementStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is RequirementStatus.AVAILABLE

    @property
    def tool(self) -> str:
        return self.requirement.name

    @property
    def available(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class RunbookPreview:
    runbook_id: str
    action: RunbookAction
    scope: RunbookExecutionScope
    command: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    script_excerpt: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def clone_safe(self) -> bool:
        return self.scope is RunbookExecutionScope.CLONE_SAFE

    @property
    def command_text(self) -> str:
        parts = [shlex.quote(part) for part in self.command]
        env_parts = [f"{key}={value}" for key, value in self.environment]
        return " ".join(env_parts + parts)

    @property
    def exit_code(self) -> None:
        return None


@dataclass(frozen=True)
class RunbookValidationReport:
    metadata: RunbookMetadata | None
    errors: tuple[str, ...] = ()
    requirement_results: tuple[object, ...] = ()

    @property
    def ok(self) -> bool:
        missing = [check for check in self.requirement_results if getattr(check, "available", True) is False]
        return not self.errors and not missing


@dataclass(frozen=True)
class RunbookCommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class RunbookConfirmationRequired(RuntimeError):
    """Raised when a high-risk runbook is run without explicit confirmation."""


def source_for_path(path: Path, runbook_root: Path) -> RunbookSource:
    try:
        relative = path.relative_to(runbook_root)
    except ValueError:
        return RunbookSource.CUSTOM
    first = relative.parts[0] if relative.parts else ""
    if first == "official":
        return RunbookSource.OFFICIAL
    if first == "training":
        return RunbookSource.TRAINING
    if first == "local":
        return RunbookSource.LOCAL
    return RunbookSource.CUSTOM


def source_rank(source: RunbookSource) -> int:
    return {
        RunbookSource.OFFICIAL: 1,
        RunbookSource.TRAINING: 2,
        RunbookSource.LOCAL: 3,
        RunbookSource.CUSTOM: 4,
    }[source]


def check_requirements(
    requirements: Iterable[str],
    *,
    available: Callable[[str], bool] | None = None,
    tool_lookup: Callable[[str], object | None] | None = None,
) -> tuple[RequirementResult, ...]:
    """Check declared tools through an injected availability predicate."""

    if tool_lookup is not None:
        predicate = lambda name: tool_lookup(name) is not None
    else:
        predicate = available or (lambda _name: False)
    results: list[RequirementResult] = []
    for name in tuple(requirements):
        requirement = RequirementCheck(name=name)
        ok = predicate(name)
        results.append(
            RequirementResult(
                requirement=requirement,
                status=RequirementStatus.AVAILABLE if ok else RequirementStatus.MISSING,
                detail="available" if ok else "missing",
            )
        )
    return tuple(results)


def command_preview(metadata: RunbookMetadata, values: dict[str, str] | None = None) -> RunbookPreview:
    """Return the resolved command preview without executing the runbook."""

    selected = values or {}
    environment: list[tuple[str, str]] = []
    for parameter in metadata.parameters:
        value = selected.get(parameter.name, parameter.default)
        environment.append((parameter.env_name, "<redacted>" if parameter.secret and value else value))
    return RunbookPreview(
        runbook_id=metadata.id,
        action=RunbookAction.PREVIEW_COMMAND,
        scope=RunbookExecutionScope.CLONE_SAFE,
        command=("bash", shlex.quote(str(metadata.path))),
        environment=tuple(environment),
        warnings=_preview_warnings(metadata),
    )


def script_preview(metadata: RunbookMetadata, *, max_lines: int = 220) -> RunbookPreview:
    """Return a bounded script excerpt; callers decide how to render it."""

    lines = metadata.path.read_text(encoding="utf-8").splitlines()
    return RunbookPreview(
        runbook_id=metadata.id,
        action=RunbookAction.PREVIEW_SCRIPT,
        scope=RunbookExecutionScope.CLONE_SAFE,
        script_excerpt="\n".join(lines[:max_lines]),
        warnings=_preview_warnings(metadata),
    )


def run_contract(metadata: RunbookMetadata) -> RunbookPreview:
    """Describe the explicit run action without performing it."""

    return RunbookPreview(
        runbook_id=metadata.id,
        action=RunbookAction.RUN,
        scope=RunbookExecutionScope.ENVIRONMENT_DEPENDENT,
        command=("bash", str(metadata.path)),
        warnings=_preview_warnings(metadata),
    )


def preview_runbook(metadata: RunbookMetadata, parameters: dict[str, str] | None = None) -> RunbookPreview:
    return command_preview(metadata, parameters)


def run_runbook(
    metadata: RunbookMetadata,
    *,
    parameters: dict[str, str] | None = None,
    confirmed: bool = False,
    cwd: Path | None = None,
    executor: Callable[..., RunbookCommandResult] | None = None,
) -> RunbookCommandResult:
    if metadata.risk in {RunbookRisk.HIGH, RunbookRisk.DESTRUCTIVE} and not confirmed:
        raise RunbookConfirmationRequired(f"{metadata.name} requires explicit confirmation")

    command = ("bash", str(metadata.path))
    run_cwd = cwd or metadata.path.parent
    env = os.environ.copy()
    selected = parameters or {}
    for parameter in metadata.parameters:
        value = selected.get(parameter.name, parameter.default)
        if value:
            env[parameter.env_name] = value

    if executor is None:
        def default_executor(command: tuple[str, ...], *, cwd: Path, env: dict[str, str]) -> RunbookCommandResult:
            started = time.monotonic()
            completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
            return RunbookCommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_seconds=time.monotonic() - started,
            )

        executor = default_executor

    result = executor(command, cwd=run_cwd, env=env)
    return RunbookCommandResult(
        command=result.command,
        exit_code=result.exit_code,
        stdout=_redact_text(result.stdout, metadata, selected),
        stderr=_redact_text(result.stderr, metadata, selected),
        duration_seconds=result.duration_seconds,
    )


def _redact_text(text: str, metadata: RunbookMetadata, selected: dict[str, str]) -> str:
    redacted = text
    for parameter in metadata.parameters:
        value = selected.get(parameter.name, parameter.default)
        if parameter.secret and value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


def _preview_warnings(metadata: RunbookMetadata) -> tuple[str, ...]:
    warnings: list[str] = []
    if metadata.risk in {RunbookRisk.HIGH, RunbookRisk.DESTRUCTIVE}:
        warnings.append(f"{metadata.risk.value} risk requires explicit confirmation before run")
    if metadata.requires:
        warnings.append("requirements are checked before run, not during clone-safe preview")
    return tuple(warnings)
