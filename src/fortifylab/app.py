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
import time
from typing import TextIO

from .tui.events import Event, TickEvent
from .tui.input import TerminalInput
from .tui.router import Router
from .tui.screen import TerminalScreen
from .tui.screens.main_menu import MainMenuScreen
from .tui.theme import TerminalStyle

# How often to wake up and dispatch a TickEvent when no key is waiting.
# This is what lets a screen with a real background operation (e.g.
# GuidedDeployScreen running a deployment step) show a "running" status
# and pick up the result once it's ready, instead of the whole TUI
# freezing on a blocking read until the next keypress.
_TICK_INTERVAL_SECONDS = 0.25


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
            started = time.monotonic()
            while running:
                event: Event | None = terminal_input.read_event(timeout=_TICK_INTERVAL_SECONDS)
                if event is None:
                    event = TickEvent(time.monotonic() - started)
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
