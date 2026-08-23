"""Guided deployment TUI prototype components."""

from .events import Event, KeyEvent, ResizeEvent, TickEvent
from .guided import (
    ControlMode,
    GuidedStep,
    StepSnapshot,
    StepState,
    build_demo_snapshot,
    render_guided_step,
)
from .menu import MenuItem, OPERATOR_MENU, render_operator_menu
from .profiles import DeploymentProfile, build_profile, expand_components, profile_components_for
from .router import Router
from .screens import (
    ApplicationsScreen,
    ConfigurationScreen,
    DiagnosticsScreen,
    GuidedDeployScreen,
    HelpScreen,
    LogsScreen,
    MainMenuScreen,
    NavigationCommand,
    NavigationKind,
    RunbooksScreen,
    Screen,
)
from .theme import TerminalStyle

__all__ = [
    "ApplicationsScreen",
    "ConfigurationScreen",
    "ControlMode",
    "DeploymentProfile",
    "DiagnosticsScreen",
    "Event",
    "GuidedDeployScreen",
    "GuidedStep",
    "HelpScreen",
    "KeyEvent",
    "LogsScreen",
    "MainMenuScreen",
    "MenuItem",
    "NavigationCommand",
    "NavigationKind",
    "OPERATOR_MENU",
    "ResizeEvent",
    "Router",
    "RunbooksScreen",
    "Screen",
    "StepSnapshot",
    "StepState",
    "TerminalStyle",
    "TickEvent",
    "build_demo_snapshot",
    "build_profile",
    "expand_components",
    "profile_components_for",
    "render_guided_step",
    "render_operator_menu",
]
