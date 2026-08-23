"""Screen stack: the direct replacement for Bash menu functions calling each
other and returning via ``return``/``break``."""

from __future__ import annotations

from .events import Event
from .screens.base import NavigationKind, Screen


class Router:
    """Owns the screen stack. The current screen is always ``stack[-1]``."""

    def __init__(self, initial_screen: Screen) -> None:
        self.stack: list[Screen] = [initial_screen]
        initial_screen.on_enter()

    @property
    def current(self) -> Screen:
        return self.stack[-1]

    def render(self) -> str:
        return self.current.render()

    def dispatch(self, event: Event) -> bool:
        """Handle one event on the current screen. Returns ``False`` when
        the router has quit (the stack is empty), ``True`` otherwise."""

        command = self.current.handle_event(event)
        if command.kind is NavigationKind.STAY:
            return True
        if command.kind is NavigationKind.PUSH:
            assert command.screen is not None
            self.stack.append(command.screen)
            command.screen.on_enter()
            return True
        if command.kind is NavigationKind.POP:
            self._pop()
            return bool(self.stack)
        if command.kind is NavigationKind.REPLACE:
            assert command.screen is not None
            self._pop()
            self.stack.append(command.screen)
            command.screen.on_enter()
            return True
        if command.kind is NavigationKind.QUIT:
            while self.stack:
                self._pop()
            return False
        raise AssertionError(f"Unhandled navigation kind: {command.kind}")

    def _pop(self) -> None:
        screen = self.stack.pop()
        screen.on_exit()
