"""Python-native ``.env`` parser, validator, and writer for Fortify Lab.

The engine is intentionally local-file only. It preserves the shape of the
operator-owned ``.env`` file while giving the future TUI a typed, testable API
for previews, validation, derived value repair, and guarded writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

from .schema import (
    DERIVED_URL_REPAIRS,
    M4_CONFIG_CONTRACT,
    ConfigField,
    ConfigFieldKind,
    field_by_key,
    redacted_value,
)


_ASSIGNMENT_RE = re.compile(
    r"^(?P<prefix>\s*)(?P<export>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<tail>.*?)(?P<newline>\r?\n?)$"
)
_HOST_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9$_.-]+(?<!-)$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:-]*$")


class ConfigValidationError(ValueError):
    """Raised when a proposed config mutation fails schema validation."""

    def __init__(self, issues: tuple["ConfigIssue", ...]):
        self.issues = issues
        message = "; ".join(f"{issue.key}: {issue.message}" for issue in issues)
        super().__init__(message or "configuration validation failed")


@dataclass(frozen=True)
class EnvValue:
    """Parsed value metadata for one assignment line."""

    value: str
    quote: str | None = None
    suffix: str = ""


@dataclass(frozen=True)
class EnvLine:
    """One line in a parsed ``.env`` document."""

    raw: str
    key: str | None = None
    value: str | None = None
    prefix: str = ""
    export: bool = False
    quote: str | None = None
    suffix: str = ""
    newline: str = "\n"

    @property
    def is_assignment(self) -> bool:
        return self.key is not None

    def render(self) -> str:
        if self.key is None or self.value is None:
            return self.raw
        keyword = "export " if self.export else ""
        quote = self.quote or ""
        return f"{self.prefix}{keyword}{self.key}={quote}{self.value}{quote}{self.suffix}{self.newline}"

    def with_value(self, value: str, *, expression: bool = False) -> "EnvLine":
        quote = '"' if expression else self.quote
        if quote is None:
            quote = "'"
        return EnvLine(
            raw="",
            key=self.key,
            value=value,
            prefix=self.prefix,
            export=self.export,
            quote=quote,
            suffix=self.suffix,
            newline=self.newline or "\n",
        )


@dataclass(frozen=True)
class ConfigIssue:
    """One validation issue suitable for TUI or CLI display."""

    key: str
    message: str
    value: str | None = None

    @property
    def display_value(self) -> str:
        return redacted_value(self.key, self.value)


@dataclass(frozen=True)
class ConfigChange:
    """A staged config update."""

    key: str
    value: str
    expression: bool = False


@dataclass(frozen=True)
class ConfigDiffEntry:
    """Redacted diff preview for one key."""

    key: str
    old: str | None
    new: str | None

    @property
    def display_old(self) -> str:
        return redacted_value(self.key, self.old)

    @property
    def display_new(self) -> str:
        return redacted_value(self.key, self.new)

    def render(self) -> str:
        return f"{self.key}: {self.display_old} -> {self.display_new}"


@dataclass(frozen=True)
class EnvBackup:
    """Backup files created before a mutating write."""

    backup_path: Path
    metadata_path: Path
    rollback_marker: Path


@dataclass(frozen=True)
class ConfigWriteResult:
    """Result of a guarded config write."""

    env_path: Path
    backup: EnvBackup | None
    changed_keys: tuple[str, ...]
    diff: tuple[ConfigDiffEntry, ...]


@dataclass
class EnvDocument:
    """Parsed ``.env`` document that preserves comments, blanks, and order."""

    lines: list[EnvLine] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> "EnvDocument":
        return cls([parse_env_line(line) for line in text.splitlines(keepends=True)])

    @classmethod
    def read(cls, path: str | Path) -> "EnvDocument":
        return cls.parse(Path(path).read_text(encoding="utf-8"))

    def render(self) -> str:
        return "".join(line.render() for line in self.lines)

    def values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in self.lines:
            if line.key is not None and line.value is not None:
                values[line.key] = line.value
        return values

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values().get(key, default)

    def stage(self, changes: tuple[ConfigChange, ...] | list[ConfigChange]) -> "EnvDocument":
        staged = EnvDocument(list(self.lines))
        for change in changes:
            staged._set(change)
        return staged

    def diff(self, changes: tuple[ConfigChange, ...] | list[ConfigChange]) -> tuple[ConfigDiffEntry, ...]:
        before = self.values()
        after = self.stage(changes).values()
        return tuple(
            ConfigDiffEntry(change.key, before.get(change.key), after.get(change.key))
            for change in changes
            if before.get(change.key) != after.get(change.key)
        )

    def repair_domain_urls(self, domain: str | None = None) -> tuple[ConfigChange, ...]:
        resolved_domain = domain or self.get("DOMAIN") or ""
        return tuple(
            ConfigChange(repair.key, repair.expression.format(domain=resolved_domain), expression=("$" in repair.expression))
            for repair in DERIVED_URL_REPAIRS
        )

    def validate(self) -> tuple[ConfigIssue, ...]:
        values = self.values()
        issues: list[ConfigIssue] = []
        for key, value in values.items():
            field = field_by_key(key)
            if field is not None:
                issues.extend(_validate_field(field, value))

        for field in _required_fields():
            value = values.get(field.key)
            if value in (None, ""):
                issues.append(ConfigIssue(field.key, "required value is missing", value))
        return tuple(issues)

    def _set(self, change: ConfigChange) -> None:
        for index, line in enumerate(self.lines):
            if line.key == change.key:
                self.lines[index] = line.with_value(change.value, expression=change.expression)
                return
        if self.lines and self.lines[-1].newline == "":
            self.lines[-1] = EnvLine(raw=self.lines[-1].raw + "\n")
        quote = '"' if change.expression else "'"
        self.lines.append(EnvLine(raw="\n"))
        self.lines.append(EnvLine(raw="", key=change.key, value=change.value, export=True, quote=quote, newline="\n"))


def parse_env_line(line: str) -> EnvLine:
    match = _ASSIGNMENT_RE.match(line)
    if not match:
        return EnvLine(raw=line)
    parsed = parse_env_value(match.group("tail"))
    return EnvLine(
        raw=line,
        key=match.group("key"),
        value=parsed.value,
        prefix=match.group("prefix"),
        export=bool(match.group("export")),
        quote=parsed.quote,
        suffix=parsed.suffix,
        newline=match.group("newline") or "",
    )


def parse_env_value(tail: str) -> EnvValue:
    value_text, suffix = _split_inline_comment(tail)
    stripped = value_text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        return EnvValue(stripped[1:-1], stripped[0], suffix)
    return EnvValue(stripped, None, suffix)


def diff_preview(path: str | Path, changes: tuple[ConfigChange, ...] | list[ConfigChange]) -> tuple[ConfigDiffEntry, ...]:
    return EnvDocument.read(path).diff(changes)


def validate_env_file(path: str | Path) -> tuple[ConfigIssue, ...]:
    return EnvDocument.read(path).validate()


def repair_domain_changes(path: str | Path, domain: str | None = None) -> tuple[ConfigChange, ...]:
    return EnvDocument.read(path).repair_domain_urls(domain)


def write_env_file(
    path: str | Path,
    changes: tuple[ConfigChange, ...] | list[ConfigChange],
    *,
    reason: str = "python-config-edit",
    backup: bool = True,
    validate: bool = True,
) -> ConfigWriteResult:
    env_path = Path(path)
    document = EnvDocument.read(env_path)
    diff = document.diff(changes)
    if not diff:
        return ConfigWriteResult(env_path=env_path, backup=None, changed_keys=(), diff=())

    staged = document.stage(changes)
    if validate:
        issues = staged.validate()
        if issues:
            raise ConfigValidationError(issues)

    created_backup = create_env_backup(env_path, reason=reason) if backup else None
    env_path.write_text(staged.render(), encoding="utf-8")
    if created_backup is not None:
        changed_keys = tuple(entry.key for entry in diff)
        with created_backup.metadata_path.open("a", encoding="utf-8") as handle:
            handle.write(f"changed_keys={','.join(changed_keys)}\n")
    return ConfigWriteResult(
        env_path=env_path,
        backup=created_backup,
        changed_keys=tuple(entry.key for entry in diff),
        diff=diff,
    )


def create_env_backup(path: str | Path, *, reason: str = "python-config-edit") -> EnvBackup:
    env_path = Path(path)
    backup_dir = env_path.parent / M4_CONFIG_CONTRACT.backup_directory
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^A-Za-z0-9_.-]+", "-", reason).strip("-.") or "python-config-edit"
    backup_path = _unique_path(backup_dir / f".env.{timestamp}.{safe_reason}.bak")
    metadata_path = backup_path.with_suffix(".meta")
    shutil.copy2(env_path, backup_path)
    metadata_path.write_text(
        f"created_by=fortifylab-python-tui\ncreated_at={timestamp}\nreason={safe_reason}\n",
        encoding="utf-8",
    )
    rollback_marker = env_path.parent / M4_CONFIG_CONTRACT.rollback_marker
    rollback_marker.write_text(f"{backup_path}\n", encoding="utf-8")
    return EnvBackup(backup_path=backup_path, metadata_path=metadata_path, rollback_marker=rollback_marker)


def _split_inline_comment(tail: str) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(tail):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in ("'", '"'):
            quote = None if quote == character else character if quote is None else quote
            continue
        if character == "#" and quote is None and (index == 0 or tail[index - 1].isspace()):
            value_end = len(tail[:index].rstrip())
            return tail[:value_end], tail[value_end:]
    return tail, ""


def _validate_field(field: ConfigField, value: str) -> tuple[ConfigIssue, ...]:
    if field.required and value == "":
        return (ConfigIssue(field.key, "required value is missing", value),)
    if value == "":
        return ()

    if field.kind == ConfigFieldKind.ENUM and field.choices and value not in field.choices:
        return (ConfigIssue(field.key, f"must be one of: {', '.join(field.choices)}", value),)
    if field.kind == ConfigFieldKind.HOSTNAME:
        return _validate_hostname(field.key, value, strict_domain=(field.key == "DOMAIN"))
    if field.kind == ConfigFieldKind.URL:
        return _validate_url(field.key, value)
    if field.kind == ConfigFieldKind.VERSION and not _VERSION_RE.match(value):
        return (ConfigIssue(field.key, "must look like a version or image tag", value),)
    if field.kind == ConfigFieldKind.PATH and "\x00" in value:
        return (ConfigIssue(field.key, "path must not contain NUL bytes", value),)
    return ()


def _validate_hostname(key: str, value: str, *, strict_domain: bool = False) -> tuple[ConfigIssue, ...]:
    if "$" in value:
        return () if _HOST_RE.match(value) else (ConfigIssue(key, "hostname expression is invalid", value),)
    pattern = _DOMAIN_RE if strict_domain else _HOST_RE
    if not pattern.match(value) or ".." in value:
        return (ConfigIssue(key, "hostname is invalid", value),)
    return ()


def _validate_url(key: str, value: str) -> tuple[ConfigIssue, ...]:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return (ConfigIssue(key, "URL must include http(s) scheme and host", value),)
    return _validate_hostname(key, parsed.netloc, strict_domain=False)


def _required_fields() -> tuple[ConfigField, ...]:
    from .schema import CONFIG_FIELDS

    return tuple(field for field in CONFIG_FIELDS if field.required)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.name[:-4] if path.name.endswith(".bak") else path.name
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}.{index}.bak")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not choose unique backup path for {path}")
