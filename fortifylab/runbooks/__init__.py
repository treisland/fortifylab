"""Runbook and help contracts for the Python TUI migration."""

from __future__ import annotations

from .catalog import HELP_ALIASES, HELP_TOPICS, discover_runbooks, get_help_topic, list_help_topics, parse_runbook_metadata
from .models import (
    HelpTopic,
    RequirementCheck,
    RequirementResult,
    RequirementStatus,
    RunbookAction,
    RunbookExecutionScope,
    RunbookMetadata,
    RunbookParameter,
    RunbookPreview,
    RunbookRisk,
    RunbookSource,
    check_requirements,
    command_preview,
    run_contract,
    script_preview,
    source_for_path,
    source_rank,
)

__all__ = [
    "HELP_ALIASES",
    "HELP_TOPICS",
    "HelpTopic",
    "RequirementCheck",
    "RequirementResult",
    "RequirementStatus",
    "RunbookAction",
    "RunbookExecutionScope",
    "RunbookMetadata",
    "RunbookParameter",
    "RunbookPreview",
    "RunbookRisk",
    "RunbookSource",
    "check_requirements",
    "command_preview",
    "discover_runbooks",
    "get_help_topic",
    "list_help_topics",
    "parse_runbook_metadata",
    "run_contract",
    "script_preview",
    "source_for_path",
    "source_rank",
]
