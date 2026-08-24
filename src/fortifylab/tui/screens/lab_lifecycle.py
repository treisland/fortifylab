"""Lab Lifecycle screen -- bulk shutdown/start chooser, the replacement
for the non-destructive options (1, 2, 4, 5) of ``lab_lifecycle_menu()``
in ``scripts/wizard/operations.sh``.

Selecting an option builds a ``DeploymentPlan`` (see
``services/lab_lifecycle_service.py``) and pushes it into a
``GuidedDeployScreen`` -- the exact same dry-run/arm/execute/background-
thread screen Guided Deploy already uses, since a bulk lifecycle action
is structurally the same thing (an ordered sequence of app operations).
The "show running" and colored-status fixes already made for Guided
Deploy apply here automatically, for free, rather than needing a third
copy of that machinery.

Destroy (options 3, 6, 7 in Bash) is not offered: every destroy path
requires typing an exact confirmation phrase, and there is no text-entry
widget in the TUI yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fortifylab.operations import OperationCatalog
from fortifylab.services.deploy_service import DeployService
from fortifylab.services.lab_lifecycle_service import apps_for_scope, build_lifecycle_plan

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen
from .guided_deploy import GuidedDeployScreen

# action, scope, label -- matches Bash's lab_lifecycle_menu() options 1/2/4/5.
_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("shutdown", "selected", "Shutdown selected profile workloads (preserve data)"),
    ("start", "selected", "Start selected profile workloads"),
    ("shutdown", "all", "Shutdown all lab deployments (preserve data)"),
    ("start", "all", "Start all lab deployments"),
)


@dataclass
class LabLifecycleScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    catalog: OperationCatalog = field(default_factory=OperationCatalog)
    env_file: Path = field(default_factory=lambda: Path(".env"))
    selected_index: int = 0

    def render(self) -> str:
        lines = [self.style.heading("Lab Lifecycle"), ""]
        for index, (_action, scope, label) in enumerate(_OPTIONS):
            marker = self.style.paint(">", "1;36") if index == self.selected_index else " "
            apps = apps_for_scope(scope, env_file=self.env_file)
            preview = ", ".join(apps) if apps else "no apps in scope"
            lines.append(f" {marker} {label}")
            lines.append(self.style.muted(f"     {preview}"))
        lines.extend(
            (
                "",
                self.style.muted("up/down to move, enter to open, q: back"),
                self.style.muted("(destroy is not available here -- use the Bash wizard's expert menu)"),
            )
        )
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("up", "k"):
            self.selected_index = (self.selected_index - 1) % len(_OPTIONS)
            return NavigationCommand.stay()
        if event.key in ("down", "j"):
            self.selected_index = (self.selected_index + 1) % len(_OPTIONS)
            return NavigationCommand.stay()
        if event.key == "enter":
            action, scope, _label = _OPTIONS[self.selected_index]
            plan = build_lifecycle_plan(action, scope, catalog=self.catalog, env_file=self.env_file)
            service = DeployService.for_plan(plan, session_id=f"lifecycle-{action}-{scope}")
            return NavigationCommand.push(GuidedDeployScreen(style=self.style, service=service))
        return NavigationCommand.stay()
