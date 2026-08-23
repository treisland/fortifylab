"""Composition root for the interactive TUI.

Constructs the terminal I/O primitives once and runs the router loop. This
is the only place that wires a live :class:`~fortifylab.tui.input.TerminalInput`
to a real screen and to :class:`~fortifylab.tui.screen.TerminalScreen`; every
screen and service underneath stays free of terminal/fd concerns and is
testable without one.
"""

from __future__ import annotations

from collections.abc import Iterable
import sys
from typing import TextIO

from .tui.events import Event
from .tui.input import TerminalInput
from .tui.router import Router
from .tui.screen import TerminalScreen
from .tui.screens.main_menu import MainMenuScreen
from .tui.theme import TerminalStyle


def run_tui(
    *,
    events: Iterable[Event] | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Run the interactive main menu until the user quits.

    ``events`` lets a caller (a test, or a future scripted-demo mode) drive
    the loop with a fixed event sequence instead of a live terminal; the
    default is a real :class:`TerminalInput` reading raw keypresses.
    """

    screen = TerminalScreen(output_stream or sys.stdout)
    router = Router(MainMenuScreen(style=TerminalStyle.from_environment()))

    if events is not None:
        screen.render(router.render())
        for event in events:
            if not router.dispatch(event):
                break
            screen.render(router.render())
        screen.close()
        return 0

    try:
        with TerminalInput(input_stream) as terminal_input:
            screen.render(router.render())
            running = True
            while running:
                event = terminal_input.read_event(timeout=None)
                if event is None:
                    continue
                running = router.dispatch(event)
                if running:
                    screen.render(router.render())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        screen.close()
    return 0
