"""Screen implementations, one per wizard menu this milestone replaces."""

from __future__ import annotations

from .applications import ApplicationsScreen
from .base import NavigationCommand, NavigationKind, Screen
from .configuration import ConfigurationScreen
from .dashboard_access import DashboardAccessScreen
from .diagnostics import DiagnosticsScreen
from .flight_plans import FlightPlansScreen
from .guided_deploy import GuidedDeployScreen
from .help import HelpScreen
from .logs import LogsScreen
from .main_menu import MainMenuScreen
from .runbooks import RunbooksScreen
from .urls_credentials import UrlsCredentialsScreen

__all__ = [
    "NavigationCommand",
    "NavigationKind",
    "Screen",
    "ApplicationsScreen",
    "ConfigurationScreen",
    "DashboardAccessScreen",
    "DiagnosticsScreen",
    "FlightPlansScreen",
    "GuidedDeployScreen",
    "HelpScreen",
    "LogsScreen",
    "MainMenuScreen",
    "RunbooksScreen",
    "UrlsCredentialsScreen",
]
