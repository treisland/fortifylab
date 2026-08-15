"""Optional dependency detection for the Python CLI/TUI migration."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec


@dataclass(frozen=True)
class DependencyCheck:
    """Availability result for an optional migration dependency."""

    name: str
    import_name: str
    purpose: str
    required: bool
    available: bool

    @property
    def state(self) -> str:
        if self.available:
            return "available"
        if self.required:
            return "missing"
        return "optional"


OPTIONAL_DEPENDENCIES: tuple[tuple[str, str, str], ...] = (
    ("rich", "rich", "polished terminal tables, panels, progress, and color"),
    ("textual", "textual", "full interactive terminal application screens"),
    ("pydantic", "pydantic", "typed config, runbook, and operation validation"),
    ("typer", "typer", "future typed command-line surface"),
)


def dependency_checks() -> tuple[DependencyCheck, ...]:
    """Return optional dependency availability without importing the packages."""

    return tuple(
        DependencyCheck(
            name=name,
            import_name=import_name,
            purpose=purpose,
            required=False,
            available=find_spec(import_name) is not None,
        )
        for name, import_name, purpose in OPTIONAL_DEPENDENCIES
    )


def migration_status_lines() -> tuple[str, ...]:
    """Human-readable status lines for the current Python migration posture."""

    return (
        "Python runtime: preview control layer for CLI/TUI operator workflows",
        "Production entrypoint: ./start_wizard.sh remains the supported Bash wizard",
        "Execution model: Python owns state, validation, rendering, and safe adapters first",
        "Bash compatibility: existing scripts remain execution adapters until replaced safely",
        "Web UI: out of active migration scope; use Kubernetes/Rancher-style tools for full cluster UI",
    )
