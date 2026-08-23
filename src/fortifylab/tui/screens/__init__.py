"""Screen implementations, one per wizard menu this milestone replaces."""

from __future__ import annotations

from .base import NavigationCommand, NavigationKind, Screen
from .main_menu import MainMenuScreen

__all__ = ["NavigationCommand", "NavigationKind", "Screen", "MainMenuScreen"]
