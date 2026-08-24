"""Task-oriented operator menu model for the Python CLI/TUI migration."""

from __future__ import annotations

from dataclasses import dataclass

from .theme import TerminalStyle


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    description: str
    state: str = "preview"


OPERATOR_MENU: tuple[MenuItem, ...] = (
    MenuItem("dashboard", "Dashboard", "Lab health, current profile, warnings, and next actions"),
    MenuItem("deploy", "Deploy / Resume", "Guided deployment, resume, repair, and deployment plan"),
    MenuItem("applications", "Applications", "SSC, LIM, ScanCentral, dashboard, and sample app lifecycle"),
    MenuItem("lab-lifecycle", "Lab Lifecycle", "Bulk shutdown/start scoped to the active profile or the whole lab"),
    MenuItem("configuration", "Configuration", ".env sections, validation, backups, and derived URL repair"),
    MenuItem("runbooks", "Runbooks", "Interactive parameter forms and safe runbook execution previews"),
    MenuItem("logs", "Logs", "Deployment logs, pod logs, follow mode, and previous container logs"),
    MenuItem("kubernetes-dashboard", "Kubernetes Dashboard", "Generate view-only or administrator access tokens"),
    MenuItem("urls-credentials", "URLs & Credentials", "Service URLs, login guidance, and credential availability"),
    MenuItem("diagnostics", "Diagnostics", "Symptom-driven checks and sanitized support bundles"),
    MenuItem("certificates", "Certificates & Trust", "mkcert root CA, lab TLS, Kubernetes secrets, and fcli trust"),
    MenuItem("tools", "Tools", "fcli readiness, versions, registry checks, and operator utilities"),
    MenuItem("help", "Help", "Onboarding, docs, troubleshooting, and keyboard guidance"),
)


def render_operator_menu(*, style: TerminalStyle | None = None) -> str:
    """Render the preview operator menu without requiring optional TUI libraries."""

    style = style or TerminalStyle.from_environment()
    lines = [style.heading("Fortify Lab Operator Console"), "", "Task workspaces:"]
    for index, item in enumerate(OPERATOR_MENU, start=1):
        lines.append(f"  {index:2d}. {item.label:<22} {style.muted(item.description)}")
    lines.extend(("", style.muted("Preview only: Bash wizard remains the production entrypoint.")))
    return "\n".join(lines) + "\n"
