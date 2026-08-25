"""Command line entrypoint for the FortifyLab Python application."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "tui":
        smoke_test = bool(args.smoke_test or os.environ.get("FORTIFYLAB_TUI_TEST_MODE"))
        return run_placeholder_tui(smoke_test=smoke_test)

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
