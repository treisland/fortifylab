"""Dashboard rendering helpers."""

from __future__ import annotations

from fortifylab.tui.theme import TerminalStyle

from .model import DashboardSnapshot


def render_dashboard(snapshot: DashboardSnapshot, *, style: TerminalStyle | None = None) -> str:
    style = style or TerminalStyle.from_environment()
    lines = [style.heading("Fortify Lab Dashboard"), ""]
    lines.append(f"Overall:  {snapshot.overall}")
    lines.append(f"Profile:  {snapshot.profile}")
    lines.append(f"Namespace:{snapshot.namespace:>9}")
    lines.append(f"Source:   {snapshot.source}")
    lines.append("")
    lines.append("Resources")
    lines.append(f"  Pods:      {snapshot.summary.ready_pods}/{snapshot.summary.pods} ready")
    lines.append(f"  PVCs:      {snapshot.summary.pvcs}")
    lines.append(f"  Ingresses: {snapshot.summary.ingresses}")
    lines.append(f"  Nodes:     {snapshot.summary.nodes_ready} ready")
    lines.append(f"  Warnings:  {snapshot.summary.warnings}")
    if snapshot.applications:
        lines.append("")
        lines.append("Applications")
        for app in snapshot.applications:
            marker = style.symbol("ok") if app.status == "Running" and app.ready.startswith("1/") else style.symbol("warn")
            lines.append(f"  {marker} {app.name:<32} {app.ready:<7} {app.status:<12} restarts={app.restarts}")
    if snapshot.warnings:
        lines.append("")
        lines.append("Warnings")
        for warning in snapshot.warnings:
            lines.append(f"  {style.symbol('warn')} {warning}")
    return "\n".join(lines) + "\n"
