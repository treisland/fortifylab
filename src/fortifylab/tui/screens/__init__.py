"""Screen implementations, one per wizard menu this milestone replaces."""

from __future__ import annotations

from .applications import ApplicationsScreen
from .base import NavigationCommand, NavigationKind, Screen
from .certificates import CertificatesScreen
from .configuration import ConfigurationScreen
from .dashboard import DashboardScreen
from .dashboard_access import DashboardAccessScreen
from .diagnostics import DiagnosticsScreen
from .flight_plans import FlightPlansScreen
from .guided_deploy import GuidedDeployScreen
from .help import HelpScreen
from .lab_lifecycle import LabLifecycleScreen
from .logs import LogsScreen
from .main_menu import MainMenuScreen
from .runbooks import RunbooksScreen
from .urls_credentials import UrlsCredentialsScreen

__all__ = [
    "NavigationCommand",
    "NavigationKind",
    "Screen",
    "ApplicationsScreen",
    "CertificatesScreen",
    "ConfigurationScreen",
    "DashboardScreen",
    "DashboardAccessScreen",
    "DiagnosticsScreen",
    "FlightPlansScreen",
    "GuidedDeployScreen",
    "HelpScreen",
    "LabLifecycleScreen",
    "LogsScreen",
    "MainMenuScreen",
    "RunbooksScreen",
    "UrlsCredentialsScreen",
]
