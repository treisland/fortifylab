"""Command line entrypoint for the FortifyLab Python application."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from .config.cli import diagnostics_command, repair_derived_command, validate_command
from .diagnostics import doctor_command
from .paths import repo_root
from .status import status_command
from .tui.app import run_placeholder_tui
from .version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fortifylab",
        description=(
            "FortifyLab CLI/TUI application. M1 provides the new entrypoint "
            "skeleton; navigation parity and operation adapters land in later "
            "migration milestones."
        ),
    )
    parser.add_argument("--version", action="version", version=f"fortifylab {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    tui = subparsers.add_parser(
        "tui",
        help="launch the placeholder terminal UI shell",
        description="Launch the M1 placeholder terminal UI shell.",
    )
    tui.add_argument(
        "--smoke-test",
        "--check",
        dest="smoke_test",
        action="store_true",
        help="render deterministic placeholder output and exit without an interactive terminal",
    )

    doctor = subparsers.add_parser(
        "doctor",
        help="run read-only Fortify Lab health diagnostics",
        description="Run clone-safe read-only Fortify Lab diagnostics.",
    )
    doctor.add_argument("--check", action="store_true", help="run deterministic noninteractive checks")
    doctor.add_argument("--strict", action="store_true", help="return nonzero when warnings or failures are present")
    doctor.add_argument("--scenario", default="ok", choices=("ok", "warning"), help=argparse.SUPPRESS)
    _add_env_file_argument(doctor)

    status = subparsers.add_parser(
        "status",
        help="print read-only Fortify Lab status summary",
        description="Print a clone-safe Fortify Lab status summary.",
    )
    status.add_argument("--check", action="store_true", help="run deterministic noninteractive status checks")

    config = subparsers.add_parser(
        "config",
        help="inspect and repair Fortify Lab .env configuration",
        description="Validate, inspect, and safely repair Fortify Lab .env configuration.",
    )
    config_subparsers = config.add_subparsers(dest="config_command", metavar="CONFIG_COMMAND")

    validate = config_subparsers.add_parser(
        "validate",
        help="validate a Fortify Lab .env file",
        description="Validate a Fortify Lab .env file and print redacted findings.",
    )
    _add_env_file_argument(validate)

    diagnostics = config_subparsers.add_parser(
        "diagnostics",
        help="print a redacted configuration diagnostics summary",
        description="Print read-only Fortify Lab domain, URL, section, and validation diagnostics.",
    )
    _add_env_file_argument(diagnostics)

    repair = config_subparsers.add_parser(
        "repair-derived",
        help="repair DOMAIN-derived host and URL values",
        description="Repair DOMAIN-derived host and URL values with dry-run and guarded write modes.",
    )
    _add_env_file_argument(repair)
    repair.add_argument("--dry-run", action="store_true", help="print the redacted diff without writing changes")
    repair.add_argument("--yes", action="store_true", help="apply the repair without an interactive confirmation prompt")

    return parser


def _add_env_file_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--env-file",
        default=None,
        help="path to the Fortify Lab .env file; defaults to the repo root .env",
    )


def _env_file_path(value: str | None) -> str:
    return value or str(repo_root() / ".env")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "tui":
        smoke_test = bool(args.smoke_test or os.environ.get("FORTIFYLAB_TUI_TEST_MODE"))
        return run_placeholder_tui(smoke_test=smoke_test)

    if args.command == "doctor":
        return doctor_command(check=bool(args.check), strict=bool(args.strict), scenario=str(args.scenario))

    if args.command == "status":
        return status_command(check=bool(args.check))

    if args.command == "config":
        if args.config_command is None:
            parser.error("config command required")
        env_file = _env_file_path(args.env_file)
        if args.config_command == "validate":
            return validate_command(env_file)
        if args.config_command == "diagnostics":
            return diagnostics_command(env_file)
        if args.config_command == "repair-derived":
            return repair_derived_command(env_file, dry_run=bool(args.dry_run), yes=bool(args.yes))

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
