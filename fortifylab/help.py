"""Offline help topic registry for the Python TUI migration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import repo_root
from .runbooks import HELP_ALIASES, HELP_TOPICS, get_help_topic


class HelpTopicNotFound(KeyError):
    """Raised when a requested offline help topic is unknown."""


@dataclass(frozen=True)
class HelpTopicRecord:
    id: str
    title: str
    offline_path: Path
    body: str
    requires_network: bool = False


class HelpRegistry:
    def __init__(self, topics: dict[str, HelpTopicRecord], aliases: dict[str, str] | None = None) -> None:
        self._topics = dict(topics)
        self._aliases = dict(aliases or {})

    @classmethod
    def from_directory(cls, directory: Path | None = None) -> "HelpRegistry":
        base = directory or repo_root() / "docs" / "help"
        root = repo_root()
        topics: dict[str, HelpTopicRecord] = {}
        for topic in HELP_TOPICS:
            path = root / topic.offline_path
            if directory is not None:
                path = base / topic.offline_path.name
            body = path.read_text(encoding="utf-8")
            topics[topic.id] = HelpTopicRecord(
                id=topic.id,
                title=topic.label,
                offline_path=path,
                body=body,
                requires_network=False,
            )
        aliases = dict(HELP_ALIASES)
        aliases["sast_controller"] = "guided/sast"
        return cls(topics, aliases)

    def lookup(self, topic_id: str) -> HelpTopicRecord:
        if topic_id in self._topics or topic_id in HELP_ALIASES:
            target = topic_id
        else:
            target = self._aliases.get(topic_id, topic_id)
        try:
            catalog_topic = get_help_topic(target)
        except KeyError as exc:
            raise HelpTopicNotFound(topic_id) from exc
        base_id = HELP_ALIASES.get(target, target)
        record = self._topics.get(base_id)
        if record is None:
            raise HelpTopicNotFound(topic_id)
        return HelpTopicRecord(
            id=catalog_topic.id,
            title=catalog_topic.label,
            offline_path=record.offline_path,
            body=record.body,
            requires_network=False,
        )

    def lookup_alias(self, alias: str) -> HelpTopicRecord:
        if alias not in self._aliases:
            raise HelpTopicNotFound(alias)
        return self.lookup(alias)


def topic_check(topic_id: str) -> str:
    topic = HelpRegistry.from_directory().lookup(topic_id)
    return f"{topic.title}\nOffline help: {topic.offline_path.relative_to(repo_root())}"
