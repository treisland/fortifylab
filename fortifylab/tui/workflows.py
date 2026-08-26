"""Workflow dispatch contracts for FortifyLab TUI screens."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from fortifylab.navigation import ActionKind, MenuItem, MenuNode, get_menu


DispatchKind = Literal["menu", "screen", "placeholder", "modeled"]


@dataclass(frozen=True)
class WorkflowScreen:
    """Minimal, testable description of a TUI workflow screen."""

    id: str
    title: str
    summary: str
    lines: tuple[str, ...] = ()

    def render(self) -> str:
        body = [self.summary, *self.lines]
        return "\n".join(line for line in body if line)


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
    "help_center": _static_screen(
        "help_center",
        "Help Center",
        "Help topic browser workflow boundary.",
        "M9.1 dispatch opens this screen; topic listing and detail navigation land in the Help/Runbooks workflow slice.",
    ),
    "runbook_library": _static_screen(
        "runbook_library",
        "Runbook Library",
        "Runbook browser workflow boundary.",
        "M9.1 dispatch opens this screen; runbook listing, detail, preview, and confirmation-gated execution land in the Help/Runbooks workflow slice.",
    ),
    "operational_guidance": _static_screen(
        "operational_guidance",
        "Operational guidance",
        "Operational guidance workflow boundary.",
        "M9.1 dispatch opens this screen; guidance browsing lands with the Help/Runbooks workflow slice.",
    ),
}


def dispatch_menu_item(
    selected: MenuItem,
    *,
    workflows: Mapping[str, WorkflowFactory] = DEFAULT_WORKFLOWS,
    menu_lookup: Callable[[str], MenuNode] = get_menu,
) -> WorkflowDispatchResult:
    """Resolve a selected menu item into a menu, workflow screen, or safe message."""

    action = selected.action
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

    factory = workflows.get(action.target)
    if factory is not None and action.kind in {ActionKind.VIEW, ActionKind.WORKFLOW, ActionKind.COMMAND}:
        screen = factory(selected)
        return WorkflowDispatchResult(
            "screen",
            f"Opened {screen.title}.",
            screen=screen,
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
