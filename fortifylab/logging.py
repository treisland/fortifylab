"""Read-only log source contracts for the Python TUI migration."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fortifylab.diagnostics import redact_diagnostic_text

DEFAULT_WIZARD_LOG_NAME = "wizard.log"
DEFAULT_LOG_TAIL_LINES = 80
DEFAULT_LOG_DETAIL_LINES = 240
MAX_LOG_READ_LINES = 1000

LogAvailability = Literal["available", "missing", "unavailable", "unsafe"]
_URL_CREDENTIAL_PATTERN = re.compile(r"(?P<prefix>https?://[^:/\s]+):[^@/\s]+@", re.IGNORECASE)
_SENSITIVE_LOG_PATH_PATTERN = re.compile(
    r"(?P<path>(?:/[^/\s]+)+/(?:token|credentials?|private[_-]?key)(?:/[^\s]*)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LogSource:
    """Known read-only log source that a TUI screen can display."""

    id: str
    label: str
    path: Path | None
    availability: LogAvailability
    detail: str = ""


@dataclass(frozen=True)
class LogReadResult:
    """Bounded, redacted log read result for TUI display."""

    source: LogSource
    lines: tuple[str, ...]
    requested_lines: int
    total_lines_read: int
    truncated: bool
    message: str

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def default_wizard_state_dir(
    *,
    env: dict[str, str] | None = None,
    state_root: Path | str | None = None,
    log_dir: Path | str | None = None,
) -> Path:
    """Return the wizard state directory without creating it."""

    if log_dir is not None:
        return _absolute_path(log_dir, "FORTIFY_WIZARD_LOG_DIR")
    if state_root is not None:
        return _absolute_path(state_root, "XDG_STATE_HOME") / "fortify-lab"

    environment = os.environ if env is None else env
    if environment.get("FORTIFY_WIZARD_LOG_DIR"):
        return _absolute_path(environment["FORTIFY_WIZARD_LOG_DIR"], "FORTIFY_WIZARD_LOG_DIR")
    if environment.get("XDG_STATE_HOME"):
        return _absolute_path(environment["XDG_STATE_HOME"], "XDG_STATE_HOME") / "fortify-lab"
    if environment.get("HOME"):
        return _absolute_path(environment["HOME"], "HOME") / ".local" / "state" / "fortify-lab"
    return Path.home() / ".local" / "state" / "fortify-lab"


def wizard_log_path(
    *,
    env: dict[str, str] | None = None,
    state_root: Path | str | None = None,
    log_dir: Path | str | None = None,
    log_file: Path | str | None = None,
    log_name: str = DEFAULT_WIZARD_LOG_NAME,
) -> Path:
    """Resolve the wizard log path without creating or mutating files."""

    environment = os.environ if env is None else env
    if log_file is not None:
        return _absolute_path(log_file, "FORTIFY_WIZARD_LOG_FILE")
    if environment.get("FORTIFY_WIZARD_LOG_FILE"):
        return _absolute_path(environment["FORTIFY_WIZARD_LOG_FILE"], "FORTIFY_WIZARD_LOG_FILE")
    name = environment.get("FORTIFY_WIZARD_LOG_NAME", log_name)
    return default_wizard_state_dir(env=environment, state_root=state_root, log_dir=log_dir) / name


def discover_log_sources(
    *,
    env: dict[str, str] | None = None,
    state_root: Path | str | None = None,
    log_dir: Path | str | None = None,
    extra_sources: tuple[LogSource, ...] = (),
) -> tuple[LogSource, ...]:
    """Discover known read-only log sources for the TUI."""

    sources = [_wizard_log_source(env=env, state_root=state_root, log_dir=log_dir)]
    sources.extend(extra_sources)
    return tuple(sources)


def read_log_tail(source: LogSource, *, lines: int = DEFAULT_LOG_TAIL_LINES) -> LogReadResult:
    """Read a bounded, redacted tail from a log source."""

    return read_log_detail(source, lines=lines)


def read_log_detail(source: LogSource, *, lines: int = DEFAULT_LOG_DETAIL_LINES) -> LogReadResult:
    """Read up to ``lines`` redacted lines from a source without mutation."""

    requested = _bounded_line_count(lines)
    if source.availability != "available" or source.path is None:
        return LogReadResult(
            source,
            (),
            requested,
            0,
            False,
            source.detail or f"{source.label} is {source.availability}.",
        )

    try:
        raw_lines = _tail_lines(source.path, requested)
    except OSError as exc:
        unavailable = LogSource(source.id, source.label, source.path, "unavailable", str(exc))
        return LogReadResult(unavailable, (), requested, 0, False, f"{source.label} is unavailable: {exc}")

    redacted = tuple(redact_log_text(line.rstrip("\n")) for line in raw_lines)
    return LogReadResult(
        source,
        redacted,
        requested,
        len(redacted),
        len(raw_lines) >= requested,
        f"Read {len(redacted)} line(s) from {source.label}.",
    )


def redact_log_text(value: str, *, extra_values: tuple[str, ...] = ()) -> str:
    """Redact log content using the shared diagnostics redactor."""

    redacted = _URL_CREDENTIAL_PATTERN.sub(lambda match: f"{match.group('prefix')}:<redacted>@", value)
    redacted = _SENSITIVE_LOG_PATH_PATTERN.sub("<sensitive-path>", redacted)
    redacted = redact_diagnostic_text(redacted, extra_values=extra_values)
    return redacted.replace("[REDACTED]", "<redacted>")


def _wizard_log_source(
    *,
    env: dict[str, str] | None = None,
    state_root: Path | str | None = None,
    log_dir: Path | str | None = None,
) -> LogSource:
    try:
        path = wizard_log_path(env=env, state_root=state_root, log_dir=log_dir)
    except ValueError as exc:
        return LogSource("wizard_log", "Wizard log", None, "unsafe", str(exc))

    if not path.exists():
        return LogSource("wizard_log", "Wizard log", path, "missing", "Wizard log has not been created yet.")
    if not path.is_file():
        return LogSource("wizard_log", "Wizard log", path, "unavailable", "Wizard log path is not a file.")
    return LogSource("wizard_log", "Wizard log", path, "available", "Wizard log is available.")


def _absolute_path(value: Path | str, name: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path.")
    return path


def _bounded_line_count(lines: int) -> int:
    if lines < 0:
        raise ValueError("lines must be a non-negative integer.")
    return min(lines, MAX_LOG_READ_LINES)


def _tail_lines(path: Path, limit: int) -> tuple[str, ...]:
    if limit == 0:
        return ()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        all_lines = handle.readlines()
    return tuple(all_lines[-limit:])
