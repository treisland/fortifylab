"""Safe subprocess primitives for the Python migration."""

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
import time
from collections.abc import Sequence


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*=\s*([^\s;&]+)"),
    re.compile(r"(?i)\b(authorization)\s*:\s*([^\r\n]+)"),
)


@dataclass(frozen=True)
class CommandResult:
    """Structured result for adapter-backed command execution."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def redact_text(text: str) -> str:
    """Mask common credential-shaped values in command output."""

    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)
    return redacted


def run_command(args: Sequence[str], *, timeout: float | None = None, cwd: str | None = None) -> CommandResult:
    """Run a command and return a redacted structured result.

    Nonzero exits are represented in the result instead of being raised. A
    timeout returns code 124 with any captured output redacted.
    """

    command = tuple(str(part) for part in args)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        timed_out = False
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        stderr = (stderr + "\n" if stderr else "") + f"Command timed out after {timeout} seconds."
    except FileNotFoundError as exc:
        # The executable itself isn't on PATH (e.g. microk8s not installed
        # yet) -- represent this as a failed result like any other command
        # error, rather than letting an OS-level exception escape into
        # every caller of this shared helper.
        timed_out = False
        returncode = 127
        stdout = ""
        stderr = str(exc)
    except PermissionError as exc:
        # The target file exists but isn't executable (e.g. a script
        # checked into git without the executable bit, which this repo's
        # own Bash wizard sidesteps by always invoking scripts as
        # `bash <path>` rather than executing them directly) -- same
        # "represent as a failed result" treatment as FileNotFoundError.
        timed_out = False
        returncode = 126
        stdout = ""
        stderr = str(exc)
    duration = time.monotonic() - started
    return CommandResult(
        args=command,
        returncode=returncode,
        stdout=redact_text(stdout),
        stderr=redact_text(stderr),
        duration_seconds=duration,
        timed_out=timed_out,
    )
