"""Preserving parser and renderer for Fortify Lab .env files."""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex


ASSIGNMENT_RE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?)(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
SECRET_KEY_RE = re.compile(r"(PASS|PASSWORD|TOKEN|SECRET|KEY|LICENSE|CREDENTIAL)")


@dataclass(frozen=True)
class EnvUpdate:
    key: str
    value: str
    expression: bool = False

    @classmethod
    def parse(cls, assignment: str) -> "EnvUpdate":
        key, separator, value = assignment.partition("=")
        if not separator:
            raise ValueError(f"Invalid assignment: {assignment}")
        if value.startswith("__EXPR__"):
            return cls(key=key, value=value.removeprefix("__EXPR__"), expression=True)
        return cls(key=key, value=value)


@dataclass(frozen=True)
class EnvDocument:
    lines: tuple[str, ...]

    def raw_value(self, key: str) -> str | None:
        value: str | None = None
        for line in self.lines:
            match = ASSIGNMENT_RE.match(line)
            if match and match.group("key") == key:
                value = match.group("value")
        return value

    def value(self, key: str) -> str | None:
        raw = self.raw_value(key)
        if raw is None:
            return None
        return _unquote(raw)

    def values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in self.lines:
            match = ASSIGNMENT_RE.match(line)
            if match:
                key = match.group("key")
                result[key] = _expand(_unquote(match.group("value")), result)
        return result

    def render(self) -> str:
        return "\n".join(self.lines).rstrip("\n") + "\n"


def parse_env_text(text: str) -> EnvDocument:
    return EnvDocument(tuple(text.splitlines()))


def apply_updates(document: EnvDocument, updates: tuple[EnvUpdate, ...]) -> EnvDocument:
    lines = list(document.lines)
    for update in updates:
        replacement = _assignment_expr(update)
        replaced = False
        next_lines: list[str] = []
        for line in lines:
            match = ASSIGNMENT_RE.match(line)
            if match and match.group("key") == update.key:
                next_lines.append(replacement)
                replaced = True
            else:
                next_lines.append(line)
        if not replaced:
            if next_lines and next_lines[-1] != "":
                next_lines.append("")
            next_lines.append(replacement)
        lines = next_lines
    return EnvDocument(tuple(lines))


def preview_changes(document: EnvDocument, updates: tuple[EnvUpdate, ...]) -> tuple[str, ...]:
    rows: list[str] = []
    for update in updates:
        old = display_value(update.key, document.value(update.key))
        new = display_value(update.key, update.value)
        rows.append(f"{update.key:<32} {old} -> {new}")
    return tuple(rows)


def display_value(key: str, value: str | None) -> str:
    if SECRET_KEY_RE.search(key):
        return "<redacted>" if value else "<unset>"
    return value or "<unset>"


def _assignment_expr(update: EnvUpdate) -> str:
    if update.expression:
        return f'export {update.key}="{update.value}"'
    return f"export {update.key}={shlex.quote(update.value)}"


def _unquote(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        return raw[1:-1]
    return raw


def _expand(value: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", replace, value)
