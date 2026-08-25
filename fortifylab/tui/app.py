"""M1 placeholder TUI shell.

The full navigation model lands in M2. This module only proves the new
entrypoint can launch a terminal UI surface and gives tests a noninteractive
contract.
"""

from __future__ import annotations


PLACEHOLDER_LINES = (
    "FortifyLab Python TUI",
    "Milestone: M1 skeleton",
    "Status: placeholder shell ready",
    "Next: M2 navigation parity",
)


def render_placeholder() -> str:
    return "\n".join(PLACEHOLDER_LINES) + "\n"


def run_placeholder_tui(*, smoke_test: bool = False) -> int:
    print(render_placeholder(), end="")
    if not smoke_test:
        print("Interactive Textual screens are scheduled for M2.")
    return 0
