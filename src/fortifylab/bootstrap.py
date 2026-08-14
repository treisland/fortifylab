"""Clone-and-run bootstrap and migration checks."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

from .runtime import RuntimePaths, runtime_paths


REQUIRED_PYTHON = (3, 10)
REQUIRED_PATHS = ("bin/fortifylab", "start_wizard.sh", "scripts/wizard", "src/fortifylab")
COMPATIBILITY_WRAPPERS = ("start_wizard.sh", "bin/fortifylab")


@dataclass(frozen=True)
class BootstrapCheck:
    name: str
    ok: bool
    detail: str


def check_python_version(version: tuple[int, int] | None = None) -> BootstrapCheck:
    current = version or sys.version_info[:2]
    ok = current >= REQUIRED_PYTHON
    required = ".".join(str(part) for part in REQUIRED_PYTHON)
    actual = ".".join(str(part) for part in current)
    return BootstrapCheck("python-version", ok, f"Python {actual}; required >= {required}")


def check_clone_layout(repo_root: Path | str) -> BootstrapCheck:
    root = Path(repo_root)
    missing = [relative for relative in REQUIRED_PATHS if not (root / relative).exists()]
    if missing:
        return BootstrapCheck("clone-layout", False, f"Missing required paths: {', '.join(missing)}")
    return BootstrapCheck("clone-layout", True, "Required clone-and-run paths are present.")


def check_compatibility_wrappers(repo_root: Path | str) -> BootstrapCheck:
    root = Path(repo_root)
    missing = [relative for relative in COMPATIBILITY_WRAPPERS if not (root / relative).exists()]
    if missing:
        return BootstrapCheck("compatibility-wrappers", False, f"Missing wrappers: {', '.join(missing)}")
    return BootstrapCheck("compatibility-wrappers", True, "Bash and Python entrypoint wrappers are present.")


def check_runtime_directories(repo_root: Path | str, *, paths: RuntimePaths | None = None) -> BootstrapCheck:
    selected = paths or runtime_paths(repo_root)
    parent = selected.log_dir.parent
    if parent.exists() and not parent.is_dir():
        return BootstrapCheck("runtime-directories", False, f"Log directory parent is not a directory: {parent}")
    writable = parent if parent.exists() else parent.parent
    if not writable.exists():
        return BootstrapCheck("runtime-directories", False, f"Runtime parent path does not exist: {writable}")
    if not _is_writable_directory(writable):
        return BootstrapCheck("runtime-directories", False, f"Runtime path is not writable: {writable}")
    return BootstrapCheck("runtime-directories", True, f"Log directory: {selected.log_dir}")


def run_bootstrap_checks(repo_root: Path | str = ".") -> tuple[BootstrapCheck, ...]:
    return (
        check_python_version(),
        check_clone_layout(repo_root),
        check_compatibility_wrappers(repo_root),
        check_runtime_directories(repo_root),
    )


def _is_writable_directory(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)
