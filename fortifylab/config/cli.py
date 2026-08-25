"""CLI bridge for Python-native Fortify Lab config operations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys

from .envfile import (
    ConfigValidationError,
    EnvDocument,
    repair_domain_changes,
    validate_env_file,
    write_env_file,
)
from .schema import CONFIG_SECTIONS, field_by_key, redacted_value


Printer = Callable[[str], None]


def validate_command(env_file: str | Path, *, print_line: Printer = print) -> int:
    env_path = Path(env_file)
    missing = _missing_env_file(env_path, print_line)
    if missing is not None:
        return missing

    issues = validate_env_file(env_path)
    print_line(f"Config validation: {env_path}")
    if not issues:
        print_line("Result: valid")
        return 0

    print_line("Result: invalid")
    for issue in issues:
        value = f" ({issue.display_value})" if issue.value is not None else ""
        print_line(f"- {issue.key}: {issue.message}{value}")
    return 1


def diagnostics_command(env_file: str | Path, *, print_line: Printer = print) -> int:
    env_path = Path(env_file)
    missing = _missing_env_file(env_path, print_line)
    if missing is not None:
        return missing

    document = EnvDocument.read(env_path)
    values = document.values()
    issues = document.validate()

    print_line(f"Config diagnostics: {env_path}")
    print_line(f"Assignments: {len(values)}")
    print_line(f"Validation: {'valid' if not issues else f'invalid ({len(issues)} findings)'}")
    _print_domain_summary(values, print_line)
    _print_section_summary(values, print_line)

    if issues:
        print_line("Findings:")
        for issue in issues:
            value = f" ({issue.display_value})" if issue.value is not None else ""
            print_line(f"- {issue.key}: {issue.message}{value}")
    return 0


def repair_derived_command(
    env_file: str | Path,
    *,
    dry_run: bool = False,
    yes: bool = False,
    stdin_is_interactive: bool | None = None,
    print_line: Printer = print,
) -> int:
    env_path = Path(env_file)
    missing = _missing_env_file(env_path, print_line)
    if missing is not None:
        return missing

    changes = repair_domain_changes(env_path)
    diff = EnvDocument.read(env_path).diff(changes)
    print_line(f"Derived config repair: {env_path}")
    if not diff:
        print_line("No derived config changes needed.")
        return 0

    print_line("Planned changes:")
    for entry in diff:
        print_line(f"- {entry.render()}")

    if dry_run:
        print_line("Dry run: no changes written.")
        return 0

    if not yes:
        interactive = sys.stdin.isatty() if stdin_is_interactive is None else stdin_is_interactive
        if not interactive:
            print_line("Refusing to write without --yes in noninteractive mode.")
            return 2
        answer = input("Apply these derived config repairs? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print_line("No changes written.")
            return 2

    try:
        result = write_env_file(env_path, changes, reason="config-repair-derived")
    except ConfigValidationError as exc:
        print_line("Repair would leave configuration invalid; no changes written.")
        for issue in exc.issues:
            value = f" ({issue.display_value})" if issue.value is not None else ""
            print_line(f"- {issue.key}: {issue.message}{value}")
        return 1

    if not result.changed_keys:
        print_line("No derived config changes needed.")
        return 0

    print_line(f"Applied {len(result.changed_keys)} changes: {', '.join(result.changed_keys)}")
    if result.backup is not None:
        print_line(f"Backup: {result.backup.backup_path}")
        print_line(f"Rollback marker: {result.backup.rollback_marker}")
    return 0


def _missing_env_file(env_path: Path, print_line: Printer) -> int | None:
    if env_path.is_file():
        return None
    print_line(f"Config file not found: {env_path}")
    return 2


def _print_domain_summary(values: dict[str, str], print_line: Printer) -> None:
    keys = (
        "DOMAIN",
        "SSC",
        "LIM",
        "SCDAST",
        "SCSAST",
        "SSC_URL",
        "LIM_URL",
        "LIM_API_URL",
        "SCDAST_URL",
        "SCSAST_URL",
        "SCSAST_CTRL_URL",
    )
    print_line("Domain and URLs:")
    for key in keys:
        print_line(f"- {key}: {redacted_value(key, values.get(key))}")


def _print_section_summary(values: dict[str, str], print_line: Printer) -> None:
    print_line("Sections:")
    for section in CONFIG_SECTIONS:
        present = sum(1 for key in section.keys if key in values and values[key] != "")
        required_missing = tuple(
            key
            for key in section.keys
            if (field := field_by_key(key)) is not None and field.required and values.get(key, "") == ""
        )
        status = "ok" if not required_missing else f"missing required: {', '.join(required_missing)}"
        print_line(f"- {section.title}: {present}/{len(section.keys)} set, {status}")
