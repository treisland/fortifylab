"""Redaction helpers for diagnostic output."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

from fortifylab.paths import repo_root

_KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|license|default_pass)\b\s*[:=]\s*([^\s]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(authorization:\s*)?bearer\s+[a-z0-9._~+/=-]+")
_SENSITIVE_PATH_PATTERN = re.compile(r"(?P<path>(?:/[^/\s]+)+/(?:\.ssh|secrets|certs|\.env)(?:/[^\s]*)?)")


def redact_diagnostic_text(value: str, *, extra_values: Iterable[str] = ()) -> str:
    redacted = value.replace(str(repo_root()), "<repo>")
    home = os.path.expanduser("~")
    if home and home != "/":
        redacted = redacted.replace(home, "<home>")
    for secret in extra_values:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    redacted = _KEY_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
    redacted = _BEARER_PATTERN.sub(lambda match: f"{match.group(1) or ''}<redacted>", redacted)
    redacted = _SENSITIVE_PATH_PATTERN.sub("<sensitive-path>", redacted)
    return redacted
