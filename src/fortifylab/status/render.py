"""Text rendering for live deployment snapshots."""

from __future__ import annotations

from .model import LiveDeploymentSnapshot


def render_snapshot(snapshot: LiveDeploymentSnapshot) -> str:
    lines = [
        f"Deployment status: {snapshot.profile}",
        f"Namespace: {snapshot.namespace}",
        f"Overall: {snapshot.overall_state.value}",
        "",
    ]
    if snapshot.tool_warnings:
        lines.append("Warnings")
        lines.extend(f"  - {warning}" for warning in snapshot.tool_warnings)
        lines.append("")
    lines.append("Steps")
    for step in snapshot.steps:
        pods = ", ".join(f"{pod.name} {pod.ready}/{pod.total} {pod.phase}" for pod in step.pods) or "no pods"
        lines.append(f"  {step.step_id:<18} {step.state.value:<12} {pods}")
        if step.hints:
            lines.append(f"    hint: {step.hints[0].message}")
    return "\n".join(lines).rstrip() + "\n"
