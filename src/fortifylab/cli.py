"""Clone-and-run Python CLI shell for Fortify Lab Phase 3."""

from __future__ import annotations

import argparse
import sys

from .tui import build_demo_snapshot, render_guided_step
from .version import __version__

_COMMAND_MESSAGES = {
    "doctor": "Python doctor command shell is available; Bash adapter is not wired yet.",
    "config": "Python config command shell is available; config engine lands in Phase 3.4.",
    "deploy": "Python deploy command shell is available; orchestration lands in Phase 3.3.",
    "logs": "Python logs command shell is available; log replacement lands in Phase 3.6.",
    "runbook": "Python runbook command shell is available; safe runner lands in Phase 3.6.",
    "tui": "Python guided TUI command shell is available; prototype lands in Phase 3.2.",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fortifylab",
        description="Fortify Lab Python CLI preview for clone-and-run lab operators.",
    )
    parser.add_argument("--version", action="version", version=f"fortifylab {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, message in _COMMAND_MESSAGES.items():
        sub = subparsers.add_parser(name, help=message)
        sub.set_defaults(message=message)
        if name == "tui":
            sub.add_argument(
                "--demo-screen",
                action="store_true",
                help="render a deterministic guided deployment prototype screen",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "tui" and args.demo_screen:
        print(render_guided_step(build_demo_snapshot()), end="")
        return 0
    print(args.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
