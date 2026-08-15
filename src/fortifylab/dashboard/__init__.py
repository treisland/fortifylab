"""Read-only dashboard snapshot components for the Python operator preview."""

from .collectors import DashboardCollector, collect_dashboard
from .model import ApplicationHealth, DashboardSnapshot, ResourceSummary, demo_snapshot
from .render import render_dashboard

__all__ = [
    "ApplicationHealth",
    "DashboardCollector",
    "DashboardSnapshot",
    "ResourceSummary",
    "collect_dashboard",
    "demo_snapshot",
    "render_dashboard",
]
