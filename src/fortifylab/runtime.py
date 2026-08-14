"""Runtime paths, logging, and compatibility reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Iterable

from .config.envfile import parse_env_text
from .config.repair import validate_hosts_and_urls
from .core.command import redact_text


DEFAULT_LOG_DIR = ".fortifylab/logs"
LOG_ENV_VAR = "FORTIFYLAB_LOG_DIR"


@dataclass(frozen=True)
class RuntimePaths:
    repo_root: Path
    log_dir: Path
    log_file: Path


@dataclass(frozen=True)
class CompatibilityItem:
    name: str
    ok: bool
    detail: str


def runtime_paths(repo_root: Path | str = ".", *, log_dir: Path | str | None = None) -> RuntimePaths:
    root = Path(repo_root).resolve()
    selected_log_dir = Path(log_dir or os.environ.get(LOG_ENV_VAR, root / DEFAULT_LOG_DIR))
    if not selected_log_dir.is_absolute():
        selected_log_dir = root / selected_log_dir
    return RuntimePaths(
        repo_root=root,
        log_dir=selected_log_dir,
        log_file=selected_log_dir / "fortifylab.log",
    )


def ensure_log_dir(paths: RuntimePaths) -> Path:
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    return paths.log_dir


def write_runtime_log(
    message: str,
    *,
    level: str = "INFO",
    event: str = "runtime",
    repo_root: Path | str = ".",
    log_dir: Path | str | None = None,
) -> Path:
    paths = runtime_paths(repo_root, log_dir=log_dir)
    ensure_log_dir(paths)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "event": event,
        "message": redact_text(message),
    }
    with paths.log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return paths.log_file


def compatibility_report(repo_root: Path | str = ".") -> tuple[CompatibilityItem, ...]:
    root = Path(repo_root)
    items: list[CompatibilityItem] = []
    env_file = root / ".env"
    if not env_file.exists():
        items.append(CompatibilityItem(".env", False, ".env is missing; run the configuration wizard before deployment."))
    else:
        document = parse_env_text(env_file.read_text(encoding="utf-8"))
        issues = validate_hosts_and_urls(document)
        if issues:
            items.append(CompatibilityItem(".env", False, f"{len(issues)} host/URL issue(s) found; run config diagnostics."))
        else:
            items.append(CompatibilityItem(".env", True, ".env host and URL values look compatible."))

    cert_dir = root / "certs"
    root_ca = cert_dir / "rootCA.pem"
    items.append(
        CompatibilityItem(
            "certificates",
            root_ca.exists(),
            "mkcert root CA is present." if root_ca.exists() else "mkcert root CA is missing; generate/export certs before browser trust setup.",
        )
    )

    secrets_dir = root / "secrets"
    license_candidates = tuple(secrets_dir.glob("*.license")) if secrets_dir.exists() else ()
    items.append(
        CompatibilityItem(
            "secrets",
            bool(license_candidates),
            "License file candidate is present." if license_candidates else "No license file candidate found under secrets/.",
        )
    )

    wrappers = ("start_wizard.sh", "bin/fortifylab")
    missing_wrappers = [path for path in wrappers if not (root / path).exists()]
    items.append(
        CompatibilityItem(
            "entrypoints",
            not missing_wrappers,
            "Bash and Python entrypoints are present." if not missing_wrappers else f"Missing entrypoints: {', '.join(missing_wrappers)}.",
        )
    )
    return tuple(items)


def render_compatibility_report(items: Iterable[CompatibilityItem]) -> tuple[str, ...]:
    return tuple(f"{item.name}: {'ok' if item.ok else 'warning'} - {item.detail}" for item in items)
