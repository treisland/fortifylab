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
from .screens import GuidedDeployScreen, MainMenuScreen, NavigationCommand, NavigationKind, Screen
from .theme import TerminalStyle

__all__ = [
    "ControlMode",
    "DeploymentProfile",
    "Event",
    "GuidedDeployScreen",
    "GuidedStep",
    "KeyEvent",
    "MainMenuScreen",
    "MenuItem",
    "NavigationCommand",
    "NavigationKind",
    "OPERATOR_MENU",
    "ResizeEvent",
    "Router",
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
