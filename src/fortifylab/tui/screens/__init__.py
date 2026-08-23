"""Screen implementations, one per wizard menu this milestone replaces."""

from __future__ import annotations

from .applications import ApplicationsScreen
from .base import NavigationCommand, NavigationKind, Screen
from .configuration import ConfigurationScreen
from .diagnostics import DiagnosticsScreen
from .flight_plans import FlightPlansScreen
from .guided_deploy import GuidedDeployScreen
from .help import HelpScreen
from .logs import LogsScreen
from .main_menu import MainMenuScreen
from .runbooks import RunbooksScreen

__all__ = [
    "NavigationCommand",
    "NavigationKind",
    "Screen",
    "ApplicationsScreen",
    "ConfigurationScreen",
    "DiagnosticsScreen",
    "FlightPlansScreen",
    "GuidedDeployScreen",
    "HelpScreen",
    "LogsScreen",
    "MainMenuScreen",
    "RunbooksScreen",
]
