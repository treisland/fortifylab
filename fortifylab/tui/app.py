"""Textual shell for the FortifyLab Python TUI migration."""

from __future__ import annotations

from fortifylab.navigation import ActionKind, MenuController, MenuItem, MenuNode, get_menu

CHECK_HEADER = (
    "FortifyLab Python TUI",
    "Milestone: M2 navigation parity",
    "Status: controller and Textual shell ready",
    "Compatibility: M1 placeholder/skeleton smoke contract retained",
)


def render_menu(menu: MenuNode, selected: MenuItem | None = None, *, message: str | None = None) -> str:
    """Render a deterministic text view of a navigation menu."""

    selected_key = selected.key if selected is not None else None
    lines = [*CHECK_HEADER, "", menu.title]
    for menu_item in menu.items:
        marker = ">" if menu_item.key == selected_key else " "
        suffix = f" [{menu_item.disabled_reason}]" if menu_item.disabled_reason else ""
        lines.append(f"{marker} {menu_item.key:>2}  {menu_item.label}{suffix}")
    if menu.notes:
        lines.append("")
        lines.extend(f"note: {note}" for note in menu.notes)
    if message:
        lines.append("")
        lines.append(message)
    return "\n".join(lines) + "\n"


def render_check() -> str:
    """Render noninteractive smoke output for CI and clone-safe checks."""

    controller = MenuController(get_menu("main"))
    return render_menu(controller.menu, controller.selected_item)


def run_tui(*, smoke_test: bool = False) -> int:
    """Run FortifyLab's TUI or a deterministic noninteractive check."""

    if smoke_test:
        print(render_check(), end="")
        return 0

    try:
        return _run_textual_app()
    except ModuleNotFoundError as exc:
        if exc.name != "textual":
            raise
        print(render_check(), end="")
        print("Interactive Textual mode requires installing requirements-python.txt.")
        return 1


def run_placeholder_tui(*, smoke_test: bool = False) -> int:
    """Backward-compatible M1 entrypoint name."""

    return run_tui(smoke_test=smoke_test)


def _run_textual_app() -> int:
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Footer, Header, Static

    class FortifyLabTui(App[None]):
        CSS = """
        Screen {
            background: $surface;
        }
        #body {
            height: 1fr;
            padding: 1 2;
        }
        #menu-title {
            text-style: bold;
            margin-bottom: 1;
        }
        #menu {
            height: 1fr;
        }
        #message {
            min-height: 3;
            color: $text-muted;
            margin-top: 1;
        }
        .disabled {
            color: $text-disabled;
        }
        """
        BINDINGS = [
            ("up", "menu_key('up')", "Up"),
            ("down", "menu_key('down')", "Down"),
            ("enter", "menu_key('enter')", "Select"),
            ("escape", "menu_key('escape')", "Back"),
            ("q", "menu_key('q')", "Quit"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.controller = MenuController(get_menu("main"))
            self.message = "Use arrows to move, number keys to jump, Enter to activate."
            self._digit_buffer = ""

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Vertical(id="body"):
                yield Static(id="menu-title")
                yield Static(id="menu")
                yield Static(id="message")
            yield Footer()

        def on_mount(self) -> None:
            self._refresh_menu()

        def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
            if event.key.isdigit():
                event.stop()
                self._handle_digit_key(event.key)
                return
            if event.character and event.character in {"m", "b", "r", "h", "?"}:
                event.stop()
                self.action_menu_key(event.character)

        def _handle_digit_key(self, digit: str) -> None:
            candidate = f"{self._digit_buffer}{digit}"
            keys = self.controller.menu.keys()
            if candidate in keys:
                has_longer_match = any(key.startswith(candidate) and key != candidate for key in keys)
                self._digit_buffer = candidate if has_longer_match else ""
                self.action_menu_key(candidate)
                return
            if any(key.startswith(candidate) for key in keys):
                self._digit_buffer = candidate
                self.message = f"Jump prefix {candidate}"
                self._refresh_menu()
                return
            self._digit_buffer = ""
            self.action_menu_key(digit)

        def action_menu_key(self, key: str) -> None:
            if not key.isdigit():
                self._digit_buffer = ""
            result = self.controller.handle_key(key)
            if result.kind == "activate" and result.activated_item is not None:
                self._handle_activation(result.activated_item)
            elif result.kind == "back":
                self._handle_back(result.action_target)
            elif result.kind == "disabled":
                self.message = result.disabled_reason or "That selection is currently disabled."
            elif result.kind == "help":
                self.message = "Help Center is modeled for M2; content wiring lands in M6."
            elif result.kind == "quit":
                self.exit()
                return
            elif result.kind == "noop":
                self.message = f"No menu action is bound to {result.raw_key!r}."
            else:
                selected = result.selected_item or self.controller.selected_item
                self.message = f"Selected {selected.key}: {selected.label}"
            self._refresh_menu()

        def _handle_activation(self, selected: MenuItem) -> None:
            self._digit_buffer = ""
            action = selected.action
            if action.kind in {ActionKind.MENU, ActionKind.WORKFLOW}:
                try:
                    self.controller = MenuController(get_menu(action.target))
                    self.message = f"Opened {selected.label}."
                    return
                except KeyError:
                    pass
            if action.placeholder or action.kind == ActionKind.PLACEHOLDER:
                self.message = f"{selected.label} is a placeholder for {action.target}."
                return
            self.message = f"{selected.label} is modeled; operation wiring starts in M3."

        def _handle_back(self, target: str | None) -> None:
            self._digit_buffer = ""
            if target:
                try:
                    self.controller = MenuController(get_menu(target))
                    self.message = "Returned."
                    return
                except KeyError:
                    pass
            if self.controller.menu.id != "main":
                self.controller = MenuController(get_menu("main"))
                self.message = "Returned to FortifyLab."
            else:
                self.message = "Already at the top menu."

        def _refresh_menu(self) -> None:
            self.query_one("#menu-title", Static).update(self.controller.menu.title)
            self.query_one("#menu", Static).update(self._menu_text())
            self.query_one("#message", Static).update(self.message)

        def _menu_text(self) -> str:
            lines = []
            selected_key = self.controller.selected_item.key
            for item in self.controller.menu.items:
                marker = ">" if item.key == selected_key else " "
                disabled = " (disabled)" if item.disabled_reason else ""
                lines.append(f"{marker} {item.key:>2}  {item.label}{disabled}")
            return "\n".join(lines)

    app = FortifyLabTui()
    app.run()
    return 0
