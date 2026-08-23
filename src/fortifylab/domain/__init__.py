"""Pure, testable domain models extracted from Bash wizard logic.

Modules here hold no I/O beyond reading local files (catalogs, .env) — no
subprocess calls, no network access, no terminal rendering. That split keeps
the wizard's business rules (what a Flight Plan is, what a scan type does)
unit-testable independent of a live cluster, and reusable by both the CLI
and the TUI.
"""

from __future__ import annotations

from .flight_plans import Catalog, FlightPlanRecord, load_catalog, merged_read_catalog, validate_catalog
from .help_center import HELP_TOPICS, HelpTopic, default_help_dir, load_topic_text
from .scan_types import ScanStep, ScanType, SastIwaJavaScan

__all__ = [
    "Catalog",
    "FlightPlanRecord",
    "load_catalog",
    "merged_read_catalog",
    "validate_catalog",
    "HELP_TOPICS",
    "HelpTopic",
    "default_help_dir",
    "load_topic_text",
    "ScanStep",
    "ScanType",
    "SastIwaJavaScan",
]
