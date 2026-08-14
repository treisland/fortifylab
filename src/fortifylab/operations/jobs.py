"""In-memory lifecycle jobs and audit records for operation execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from fortifylab.core.command import redact_text
from fortifylab.runtime import write_runtime_log

from .catalog import OperationCatalog, OperationSpec
from .runner import OperationExecution, OperationRunner, summarize_output


class OperationJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OperationAuditEntry:
    audit_id: str
    job_id: str
    operation_id: str
    action: str
    status: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    detail: dict[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "job_id": self.job_id,
            "operation_id": self.operation_id,
            "action": self.action,
            "status": self.status,
            "message": redact_text(self.message),
            "timestamp": self.timestamp,
            "detail": _redacted_payload(self.detail),
        }


@dataclass(frozen=True)
class OperationJob:
    job_id: str
    operation_id: str
    command: tuple[str, ...]
    execute: bool = False
    status: OperationJobStatus = OperationJobStatus.QUEUED
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    ended_at: str | None = None
    duplicate_of: str | None = None
    message: str = "Operation job queued."
    execution: OperationExecution | None = None
    audit: tuple[OperationAuditEntry, ...] = ()

    @property
    def active(self) -> bool:
        return self.status in (OperationJobStatus.QUEUED, OperationJobStatus.RUNNING)

    @property
    def ok(self) -> bool:
        return self.status in (OperationJobStatus.COMPLETE, OperationJobStatus.REJECTED)

    def to_api_dict(self) -> dict[str, Any]:
        return operation_job_payload(self)


@dataclass(frozen=True)
class OperationJobRequest:
    operation_id: str
    execute: bool = False
    confirmation: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationJobRequest":
        operation_id = str(payload.get("operation_id") or payload.get("id") or "").strip()
        if not operation_id:
            raise ValueError("operation_id is required.")
        return cls(
            operation_id=operation_id,
            execute=bool(payload.get("execute", False)),
            confirmation=str(payload["confirmation"]) if payload.get("confirmation") is not None else None,
        )


class OperationJobManager:
    """Track operation execution without persisting secrets or raw command output."""

    def __init__(
        self,
        catalog: OperationCatalog | None = None,
        runner: OperationRunner | None = None,
        *,
        max_jobs: int = 100,
    ) -> None:
        self.catalog = catalog or OperationCatalog()
        self.runner = runner or OperationRunner()
        self.max_jobs = max_jobs
        self._lock = Lock()
        self._jobs: dict[str, OperationJob] = {}
        self._audit: list[OperationAuditEntry] = []

    def submit(self, request: OperationJobRequest) -> tuple[OperationJob, bool]:
        spec = self.catalog.get(request.operation_id)
        with self._lock:
            duplicate = self._active_duplicate(spec.operation_id, request.execute)
            if duplicate:
                job = replace(
                    duplicate,
                    duplicate_of=duplicate.job_id,
                    message="Duplicate operation already active; returning existing job.",
                )
                return job, False

            job = OperationJob(
                job_id=f"opjob-{uuid4().hex[:12]}",
                operation_id=spec.operation_id,
                command=spec.command,
                execute=request.execute,
                message="Operation job queued.",
            )
            job = self._record_locked(job, "job.queued", job.status.value, "Operation job queued.", {"execute": request.execute})
            self._jobs[job.job_id] = job
            self._prune_locked()

        thread = Thread(target=self._run_job, args=(job.job_id, spec, request), daemon=True)
        thread.start()
        return job, True

    def list_jobs(self) -> tuple[OperationJob, ...]:
        with self._lock:
            return tuple(sorted(self._jobs.values(), key=lambda job: job.requested_at, reverse=True))

    def get_job(self, job_id: str) -> OperationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def audit_entries(self) -> tuple[OperationAuditEntry, ...]:
        with self._lock:
            return tuple(self._audit)

    def operation_payloads(self) -> list[dict[str, Any]]:
        return [operation_spec_payload(spec) for spec in self.catalog.list()]

    def _run_job(self, job_id: str, spec: OperationSpec, request: OperationJobRequest) -> None:
        with self._lock:
            current = self._jobs[job_id]
            current = replace(current, status=OperationJobStatus.RUNNING, started_at=_now(), message="Operation job running.")
            self._jobs[job_id] = self._record_locked(current, "job.started", current.status.value, "Operation job started.", {"execute": request.execute})

        execution = self.runner.run(spec, execute=request.execute, confirmation=request.confirmation)
        status = OperationJobStatus.COMPLETE if execution.ok else OperationJobStatus.FAILED
        if not execution.executed:
            status = OperationJobStatus.COMPLETE if execution.ok else OperationJobStatus.REJECTED
        message = execution.summary()

        with self._lock:
            current = self._jobs[job_id]
            current = replace(current, status=status, ended_at=execution.ended_at or _now(), message=message, execution=execution)
            self._jobs[job_id] = self._record_locked(
                current,
                "job.finished",
                status.value,
                message or "Operation job finished.",
                {
                    "executed": execution.executed,
                    "returncode": execution.returncode,
                    "timed_out": execution.timed_out,
                    "log_file": execution.log_file,
                },
            )

    def _active_duplicate(self, operation_id: str, execute: bool) -> OperationJob | None:
        for job in self._jobs.values():
            if job.operation_id == operation_id and job.execute == execute and job.active:
                return job
        return None

    def _record_locked(self, job: OperationJob, action: str, status: str, message: str, detail: dict[str, Any]) -> OperationJob:
        entry = OperationAuditEntry(
            audit_id=f"audit-{uuid4().hex[:12]}",
            job_id=job.job_id,
            operation_id=job.operation_id,
            action=action,
            status=status,
            message=summarize_output(message),
            detail=detail,
        )
        self._audit.append(entry)
        write_runtime_log(
            f"operation_job job_id={job.job_id} operation_id={job.operation_id} action={action} status={status} message={entry.message}",
            event="operation.audit",
        )
        return replace(job, audit=(*job.audit, entry))

    def _prune_locked(self) -> None:
        if len(self._jobs) <= self.max_jobs:
            return
        removable = [job for job in sorted(self._jobs.values(), key=lambda item: item.requested_at) if not job.active]
        for job in removable[: max(0, len(self._jobs) - self.max_jobs)]:
            self._jobs.pop(job.job_id, None)


def operation_spec_payload(spec: OperationSpec) -> dict[str, Any]:
    return {
        "id": spec.operation_id,
        "label": spec.label,
        "kind": spec.kind.value,
        "impact": spec.impact.value,
        "mutates": spec.mutates,
        "requires_confirmation": bool(spec.confirmation_phrase),
        "confirmation_phrase": spec.confirmation_phrase,
        "warning": spec.warning,
        "command_preview": list(spec.command),
    }


def operation_execution_payload(execution: OperationExecution | None) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "operation_id": execution.operation_id,
        "executed": execution.executed,
        "ok": execution.ok,
        "detail": execution.summary(),
        "started_at": execution.started_at,
        "ended_at": execution.ended_at,
        "duration_seconds": execution.duration_seconds,
        "returncode": execution.returncode,
        "timed_out": execution.timed_out,
        "log_file": execution.log_file,
        "stdout_summary": summarize_output(execution.stdout),
        "stderr_summary": summarize_output(execution.stderr),
    }


def operation_job_payload(job: OperationJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "operation_id": job.operation_id,
        "command_preview": list(job.command),
        "execute": job.execute,
        "status": job.status.value,
        "requested_at": job.requested_at,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "duplicate_of": job.duplicate_of,
        "message": summarize_output(job.message),
        "execution": operation_execution_payload(job.execution),
        "audit": [entry.to_api_dict() for entry in job.audit],
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redacted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: redact_text(str(value)) if isinstance(value, str) else value for key, value in payload.items()}
