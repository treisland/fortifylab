"""Offline Help Center topic catalog.

Ports the topic table from ``scripts/lib/help.sh``'s ``HELP_TOPIC_ID`` /
``HELP_TOPIC_LABEL`` / ``HELP_TOPIC_FILE`` arrays -- specifically the 13
topics ``help_center()``'s own interactive menu lists (the Bash script also
defines ``guided/*`` and ``troubleshooting/*`` alias IDs used by *other*
screens for contextual help, but those never appear in the Help Center menu
itself, so they're out of scope here).

Content is the same committed, offline, read-only plain-text files in
``docs/help/*.txt`` the Bash Help Center reads -- this module does not
duplicate their content, only the topic list and a loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HelpTopic:
    topic_id: str
    label: str
    filename: str


HELP_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic("overview", "System overview", "overview.txt"),
    HelpTopic("architecture", "Dependencies and data flow", "architecture.txt"),
    HelpTopic("ssc", "Software Security Center (SSC)", "ssc.txt"),
    HelpTopic("sast", "ScanCentral SAST", "sast.txt"),
    HelpTopic("dast", "ScanCentral DAST", "dast.txt"),
    HelpTopic("lim", "License and Infrastructure Manager (LIM)", "lim.txt"),
    HelpTopic("mysql", "MySQL", "mysql.txt"),
    HelpTopic("postgresql", "PostgreSQL", "postgresql.txt"),
    HelpTopic("dashboard", "Kubernetes Dashboard", "dashboard.txt"),
    HelpTopic("roles", "Roles and learning paths", "roles.txt"),
    HelpTopic("glossary", "Glossary", "glossary.txt"),
    HelpTopic("urls", "URLs and interfaces", "urls.txt"),
    HelpTopic("lab-scope", "Lab deployment vs Fortify products", "lab-scope.txt"),
)


def default_help_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "help"


def load_topic_text(topic: HelpTopic, *, help_dir: Path | None = None) -> str:
    """Read a topic's offline content. Raises FileNotFoundError if the
    committed doc is missing -- callers should show that as an error, the
    same way the Bash ``help_render_topic`` does, not silently substitute
    text."""

    directory = help_dir or default_help_dir()
    return (directory / topic.filename).read_text(encoding="utf-8")
