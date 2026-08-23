"""Screen implementations, one per wizard menu this milestone replaces."""

from __future__ import annotations

from .applications import ApplicationsScreen
from .base import NavigationCommand, NavigationKind, Screen
from .configuration import ConfigurationScreen
from .guided_deploy import GuidedDeployScreen
from .logs import LogsScreen
from .main_menu import MainMenuScreen

__all__ = [
    "NavigationCommand",
    "NavigationKind",
    "Screen",
    "ApplicationsScreen",
    "ConfigurationScreen",
    "GuidedDeployScreen",
    "LogsScreen",
    "MainMenuScreen",
]
