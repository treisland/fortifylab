"""Guided deployment pipeline payloads for the web console."""

from __future__ import annotations

from typing import Any

from fortifylab.status import LiveDeploymentSnapshot, LiveStepStatus

_TERMINAL_STATES = {"complete", "failed", "blocked"}
_ACTIVE_STATES = {"in_progress", "running", "waiting"}


def guided_pipeline_payload(guide: dict[str, Any], snapshot: LiveDeploymentSnapshot, jobs: dict[str, Any]) -> dict[str, Any]:
    """Build a compact, live-first pipeline model from guided deployment evidence."""
    steps = list(guide.get("steps") or [])
    live_by_id = {step.step_id: step for step in snapshot.steps}
    active_jobs = list(jobs.get("active_jobs") or [])
    stages = [pipeline_stage(step, live_by_id.get(str(step.get("step_id") or ""))) for step in steps]
    active_stage = next((stage for stage in stages if stage["state"] in _ACTIVE_STATES), None)
    blocked_stage = next((stage for stage in stages if stage["state"] in {"failed", "blocked"}), None)
    complete_count = len([stage for stage in stages if stage["state"] == "complete"])
    overall_state = str(guide.get("overall_state") or snapshot.overall_state.value)
    return {
        "version": 1,
        "kind": "guided-deployment",
        "profile": guide.get("profile") or snapshot.profile,
        "overall_state": overall_state,
        "progress": {
            "complete": complete_count,
            "total": len(stages),
            "percent": round((complete_count / len(stages)) * 100) if stages else 0,
        },
        "active_stage_id": (blocked_stage or active_stage or next((stage for stage in stages if stage["state"] != "complete"), None) or {}).get("id"),
        "stages": stages,
        "active_jobs": active_jobs,
        "controls": {
            "refresh_endpoint": "/api/pipeline/guided",
            "jobs_endpoint": "/api/jobs",
            "logs_panel": "logs",
            "diagnostics_panel": "health",
            "supports_reconnect": True,
            "animation": "subtle-flow",
            "reduced_motion": "supported",
        },
        "state_sources": {
            "deployment": "live-first",
            "jobs": "runtime",
            "history": "not-authoritative",
        },
    }


def pipeline_stage(step: dict[str, Any], live_step: LiveStepStatus | None) -> dict[str, Any]:
    state = str(step.get("state") or "pending")
    pods = list(step.get("pods") or [])
    finding_count = int(step.get("hint_count") or 0)
    if live_step:
        pods = [pod.name for pod in live_step.pods]
        finding_count = len(live_step.hints)
    actions = ["open-step"]
    if pods:
        actions.append("view-logs")
    if finding_count or state in {"blocked", "failed"}:
        actions.append("view-diagnostics")
    return {
        "id": step.get("step_id") or "step",
        "index": step.get("index"),
        "label": step.get("label") or step.get("step_id") or "Deployment step",
        "state": state,
        "detail": step.get("detail") or "Waiting for live deployment evidence.",
        "pods": pods,
        "finding_count": finding_count,
        "elapsed_seconds": live_step.elapsed_seconds if live_step else step.get("elapsed_seconds", 0),
        "is_terminal": state in _TERMINAL_STATES,
        "actions": actions,
    }
