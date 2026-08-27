"""Textual shell for the FortifyLab Python TUI migration."""

from __future__ import annotations

from fortifylab.navigation import ActionKind, ActionRef, MenuController, MenuItem, MenuNode, get_menu, normalize_menu_key
from fortifylab.tui.workflows import WorkflowScreen, dispatch_menu_item

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


def workflow_key_from_event(event) -> str | None:  # type: ignore[no-untyped-def]
    """Return normalized workflow key input from a Textual key event."""

    key = getattr(event, "key", None)
    if isinstance(key, str) and key.isdigit():
        return key
    character = getattr(event, "character", None)
    if isinstance(character, str) and len(character) == 1 and character.isprintable():
        return character
    if isinstance(key, str):
        normalized = normalize_menu_key(key)
        if normalized in {"enter", "up", "down", "back", "quit", "help"}:
            return normalized
    return None


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
            self.workflow_screen: WorkflowScreen | None = None
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
            if self.workflow_screen is not None:
                workflow_key = workflow_key_from_event(event)
                if workflow_key is not None:
                    event.stop()
                    self.action_menu_key(workflow_key)
                return
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
            if self.workflow_screen is not None:
                self._handle_workflow_screen_key(key)
                return
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
            dispatch = dispatch_menu_item(selected)
            if dispatch.kind == "menu" and dispatch.menu is not None:
                self.controller = MenuController(dispatch.menu)
                self.workflow_screen = None
                self.message = dispatch.message
                return
            if dispatch.kind == "screen" and dispatch.screen is not None:
                self.workflow_screen = dispatch.screen
                self.message = dispatch.message
                return
            self.message = dispatch.message

        def _open_workflow_target(self, target: str, fallback_message: str) -> None:
            selected = MenuItem("handoff", target.replace("_", " ").title(), ActionRef(ActionKind.WORKFLOW, target, placeholder=False))
            dispatch = dispatch_menu_item(selected)
            if dispatch.kind == "menu" and dispatch.menu is not None:
                self.controller = MenuController(dispatch.menu)
                self.workflow_screen = None
                self.message = dispatch.message
                return
            if dispatch.kind == "screen" and dispatch.screen is not None:
                self.workflow_screen = dispatch.screen
                self.message = dispatch.message
                return
            self.message = fallback_message

        def _handle_back(self, target: str | None) -> None:
            self._digit_buffer = ""
            if self.workflow_screen is not None:
                self.workflow_screen = None
                self.message = "Returned."
                return
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

        def _handle_workflow_screen_key(self, key: str) -> None:
            normalized = key if key == "r" else normalize_menu_key(key)
            if normalized == "quit":
                self.exit()
                return
            if self.workflow_screen is not None:
                result = self.workflow_screen.handle_key(normalized)
                self.message = result.message
                if result.open_target is not None:
                    self._open_workflow_target(result.open_target, result.message)
                    self._refresh_menu()
                    return
                if result.exit_screen:
                    self.workflow_screen = None
                self._refresh_menu()
                return
            if normalized == "back":
                self._handle_back(None)
                self._refresh_menu()
                return
            if normalized == "help":
                self.message = "Help is available from the Help Center workflow."
            else:
                self.message = f"No workflow screen action is bound to {key!r}."
            self._refresh_menu()

        def _refresh_menu(self) -> None:
            if self.workflow_screen is not None:
                self.query_one("#menu-title", Static).update(self.workflow_screen.title)
                self.query_one("#menu", Static).update(self.workflow_screen.render())
            else:
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
