"""Workflow dispatch contracts for FortifyLab TUI screens."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from fortifylab.navigation import ActionKind, MenuItem, MenuNode, get_menu


DispatchKind = Literal["menu", "screen", "placeholder", "modeled"]


@dataclass(frozen=True)
class WorkflowKeyResult:
    """Result of handling a key inside a workflow screen."""

    message: str
    exit_screen: bool = False


@dataclass
class WorkflowScreen:
    """Minimal, testable description of a TUI workflow screen."""

    id: str
    title: str
    summary: str
    lines: tuple[str, ...] = ()

    def render(self) -> str:
        body = [self.summary, *self.lines]
        return "\n".join(line for line in body if line)

    def handle_key(self, key: str) -> WorkflowKeyResult:
        """Handle a workflow keypress; rich screens override this."""

        return WorkflowKeyResult(f"No workflow screen action is bound to {key!r}.")


@dataclass(frozen=True)
class WorkflowDispatchResult:
    """Result of resolving a selected navigation action."""

    kind: DispatchKind
    message: str
    menu: MenuNode | None = None
    screen: WorkflowScreen | None = None
    selected_item: MenuItem | None = None


WorkflowFactory = Callable[[MenuItem], WorkflowScreen]


def _static_screen(screen_id: str, title: str, summary: str, *lines: str) -> WorkflowFactory:
    def build_screen(_selected: MenuItem) -> WorkflowScreen:
        return WorkflowScreen(screen_id, title, summary, tuple(lines))

    return build_screen


DEFAULT_WORKFLOWS: Mapping[str, WorkflowFactory] = {
    "setup_readiness": lambda _selected: _build_setup_readiness_screen(),
    "configuration_editor": lambda _selected: _build_config_editor_screen(),
    "diagnostics": lambda _selected: _build_diagnostics_screen(),
    "cluster_snapshot": lambda _selected: _build_status_screen(),
    "doctor": lambda _selected: _build_doctor_screen(),
    "status": lambda _selected: _build_status_screen(),
    "logs": lambda _selected: _build_logs_screen(),
    "wizard_log": lambda _selected: _build_wizard_log_screen(),
    "help_center": lambda _selected: _build_help_center_screen(),
    "runbook_library": lambda _selected: _build_runbook_library_screen(),
    "operational_guidance": _static_screen(
        "operational_guidance",
        "Operational guidance",
        "Operational guidance workflow boundary.",
        "M9.1 dispatch opens this screen; guidance browsing lands with the Help/Runbooks workflow slice.",
    ),
}


def build_config_workflow(env_file=None) -> WorkflowScreen:
    from fortifylab.tui.config import ConfigEditorScreen

    return ConfigEditorScreen(env_file=env_file)


def build_setup_readiness_workflow(snapshot_provider=None, env_file=None, doctor_report_provider=None, status_provider=None) -> WorkflowScreen:
    from fortifylab.tui.readiness import SetupReadinessScreen

    return SetupReadinessScreen(
        snapshot_provider=snapshot_provider,
        env_file=env_file,
        doctor_report_provider=doctor_report_provider,
        status_provider=status_provider,
    )


def build_help_workflow(help_root=None) -> WorkflowScreen:
    from fortifylab.tui.help_runbooks import HelpCenterScreen

    return HelpCenterScreen(help_root=help_root)


def build_runbook_workflow(runbook_root=None) -> WorkflowScreen:
    from fortifylab.tui.help_runbooks import RunbookLibraryScreen

    return RunbookLibraryScreen(runbook_root=runbook_root)


def build_diagnostics_workflow(doctor_report_provider=None, status_provider=None) -> WorkflowScreen:
    from fortifylab.tui.diagnostics_status import DiagnosticsScreen

    return DiagnosticsScreen(doctor_report_provider=doctor_report_provider, status_provider=status_provider)


def build_doctor_workflow(doctor_report_provider=None) -> WorkflowScreen:
    from fortifylab.tui.diagnostics_status import DoctorScreen

    return DoctorScreen(doctor_report_provider=doctor_report_provider)


def build_status_workflow(status_provider=None) -> WorkflowScreen:
    from fortifylab.tui.diagnostics_status import StatusScreen

    return StatusScreen(status_provider=status_provider)


def build_logs_workflow(log_sources=None) -> WorkflowScreen:
    from fortifylab.tui.logs import LogsWorkflowScreen

    return LogsWorkflowScreen(log_sources=log_sources)


def build_wizard_log_workflow(log_sources=None) -> WorkflowScreen:
    from fortifylab.tui.logs import WizardLogWorkflowScreen

    return WizardLogWorkflowScreen(log_sources=log_sources)


def _build_config_editor_screen() -> WorkflowScreen:
    return build_config_workflow()


def _build_setup_readiness_screen() -> WorkflowScreen:
    return build_setup_readiness_workflow()


def _build_diagnostics_screen() -> WorkflowScreen:
    return build_diagnostics_workflow()


def _build_doctor_screen() -> WorkflowScreen:
    return build_doctor_workflow()


def _build_status_screen() -> WorkflowScreen:
    return build_status_workflow()


def _build_logs_screen() -> WorkflowScreen:
    return build_logs_workflow()


def _build_wizard_log_screen() -> WorkflowScreen:
    return build_wizard_log_workflow()


def _build_help_center_screen() -> WorkflowScreen:
    return build_help_workflow()


def _build_runbook_library_screen() -> WorkflowScreen:
    return build_runbook_workflow()


def _build_lifecycle_screen_if_supported(selected: MenuItem) -> WorkflowScreen | None:
    try:
        from fortifylab.tui.lifecycle import build_lifecycle_workflow, resolve_lifecycle_action

        resolve_lifecycle_action(selected.action.target)
    except KeyError:
        return None
    return build_lifecycle_workflow(selected)


def dispatch_menu_item(
    selected: MenuItem,
    *,
    workflows: Mapping[str, WorkflowFactory] = DEFAULT_WORKFLOWS,
    menu_lookup: Callable[[str], MenuNode] = get_menu,
) -> WorkflowDispatchResult:
    """Resolve a selected menu item into a menu, workflow screen, or safe message."""

    action = selected.action
    factory = workflows.get(action.target)
    if factory is not None and action.kind in {
        ActionKind.VIEW,
        ActionKind.WORKFLOW,
        ActionKind.COMMAND,
        ActionKind.PLACEHOLDER,
    }:
        screen = factory(selected)
        return WorkflowDispatchResult(
            "screen",
            f"Opened {screen.title}.",
            screen=screen,
            selected_item=selected,
        )

    if action.kind in {ActionKind.MENU, ActionKind.WORKFLOW}:
        try:
            menu = menu_lookup(action.target)
        except KeyError:
            pass
        else:
            return WorkflowDispatchResult(
                "menu",
                f"Opened {selected.label}.",
                menu=menu,
                selected_item=selected,
            )

    if action.kind in {ActionKind.VIEW, ActionKind.WORKFLOW, ActionKind.COMMAND, ActionKind.PLACEHOLDER}:
        lifecycle_screen = _build_lifecycle_screen_if_supported(selected)
        if lifecycle_screen is not None:
            return WorkflowDispatchResult(
                "screen",
                f"Opened {lifecycle_screen.title}.",
                screen=lifecycle_screen,
                selected_item=selected,
            )

    if action.placeholder or action.kind == ActionKind.PLACEHOLDER:
        return WorkflowDispatchResult(
            "placeholder",
            f"{selected.label} is a placeholder for {action.target}.",
            selected_item=selected,
        )

    return WorkflowDispatchResult(
        "modeled",
        f"{selected.label} is modeled; operation wiring starts in a later milestone.",
        selected_item=selected,
    )
