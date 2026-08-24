"""Applications screen -- the interactive replacement for ``apps_menu()``'s/
``sample_apps_menu()``'s shared ``app_action_menu()`` in
``scripts/wizard/operations.sh``, for the apps ``OperationCatalog`` already
knows how to run (``ssc``, ``lim``, ``mysql``, ``postgresql``, and the
sample apps ``juice-shop``, ``webgoat``, ``dvwa``).

Two levels, matching Bash's shape: a list of apps with live pod status
(``app_status()`` -- "N/M running"/"N/M ready"/"not deployed", the same
three states and colors), then a per-app menu (Start/Upgrade, Stop, Logs,
Show URL & credentials) once one is selected. Bash keeps core apps and
sample apps on separate menu numbers, but the underlying shape is
identical, so this one screen covers both -- sample apps are just labeled
"(sample)".

Not wired here, same reason in both cases -- no text-entry widget yet:
- **Destroy**: requires typing an exact confirmation phrase
  (``OperationSpec.confirmation_phrase``, e.g. ``"DESTROY ssc"``).
- **Scale workers** (SAST/DAST only, and SAST/DAST themselves aren't in
  this screen's app list yet -- see the roadmap): Bash's ``scale_workers``
  reads a free-typed replica count.

A real (``execute=True``) start/stop runs on a background thread, the
same mechanism ``GuidedDeployScreen``/``DeployService`` use: without it, a
Helm-backed start that takes minutes would freeze the whole TUI with no
visual feedback. Dry-run previews stay synchronous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import threading

from fortifylab.config.envfile import display_value
from fortifylab.config.store import ConfigStore
from fortifylab.operations import OperationCatalog, OperationExecution, OperationRunner
from fortifylab.operations.catalog import OperationSpec
from fortifylab.services.app_status_service import AppStatus, AppStatusService

from ..events import Event, KeyEvent, TickEvent
from ..theme import TerminalStyle
from .base import Armable, NavigationCommand, Screen
from .logs import LogsScreen

# app_id, label, pod prefix (app_status()), log-scope step_id
# (tui.profiles.LOG_SCOPES), .env URL key (empty if Bash shows none).
_APPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("ssc", "Software Security Center", "ssc-webapp", "ssc", "SSC_URL"),
    ("lim", "License and Infrastructure Manager", "lim", "lim", "LIM_URL"),
    ("mysql", "MySQL", "mysql", "mysql", ""),
    ("postgresql", "PostgreSQL", "postgresql", "postgresql", ""),
    ("juice-shop", "Juice Shop (sample)", "sample-juice-shop", "sample_juice_shop", "JUICE_SHOP_URL"),
    ("webgoat", "WebGoat (sample)", "sample-webgoat", "sample_webgoat", "WEBGOAT_URL"),
    ("dvwa", "DVWA (sample)", "sample-dvwa", "sample_dvwa", "DVWA_URL"),
)

# Matches show_app_creds()'s per-app cases in scripts/wizard/operations.sh;
# apps with no case there (mysql/postgresql/sample apps) show URL only.
_LOGIN_HINTS: dict[str, tuple[str, ...]] = {
    "ssc": ("Login username: admin", "Password: refer to the SSC documentation for the default password."),
    "lim": ("Login username: lim_admin", "Password: stored in Kubernetes Secret lim-admin-credentials"),
}

_APP_ACTIONS: tuple[tuple[str, str], ...] = (
    ("start", "Start / Upgrade"),
    ("stop", "Stop"),
    ("logs", "Logs"),
    ("credentials", "Show URL & credentials"),
)


class _Stage(str, Enum):
    LIST = "list"
    APP_MENU = "app_menu"


@dataclass
class ApplicationsScreen(Armable, Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    catalog: OperationCatalog = field(default_factory=OperationCatalog)
    runner: OperationRunner = field(default_factory=OperationRunner)
    status_service: AppStatusService = field(default_factory=AppStatusService)
    env_file: Path = field(default_factory=lambda: Path(".env"))
    apps: tuple[tuple[str, str, str, str, str], ...] = _APPS
    stage: _Stage = _Stage.LIST
    selected_app_index: int = 0
    selected_action_index: int = 0
    statuses: dict[str, AppStatus] = field(default_factory=dict)
    show_credentials: bool = False
    last_execution: OperationExecution | None = None
    running: bool = False
    _execution_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)
    _running_thread: threading.Thread | None = field(default=None, init=False, repr=False, compare=False)
    _pending_execution: OperationExecution | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.env_file.exists():
            namespace = ConfigStore(self.env_file).load().values().get("NAMESPACE")
            if namespace:
                self.status_service.namespace = namespace
        self._refresh_statuses()

    @property
    def is_executing(self) -> bool:
        with self._execution_lock:
            return self._running_thread is not None

    def _refresh_statuses(self) -> None:
        prefixes = {app_id: prefix for app_id, _label, prefix, _step, _url in self.apps}
        self.statuses = self.status_service.statuses(prefixes)

    def _status_text(self, app_id: str) -> tuple[str, str]:
        """Return (text, color_name), matching app_status()'s three states
        and colors: green "N/N running", yellow "N/M ready", dim "not deployed"."""

        status = self.statuses.get(app_id, AppStatus())
        if not status.deployed:
            return "not deployed", "muted"
        if status.fully_ready:
            return f"{status.ready}/{status.total} running", "ok"
        return f"{status.ready}/{status.total} ready", "warn"

    def render(self) -> str:
        if self.stage is _Stage.APP_MENU:
            return self._render_app_menu()
        return self._render_list()

    def _render_list(self) -> str:
        lines = [self.style.heading("Applications"), "", f"  {'':3}{'Name':<36}{'Status'}"]
        for index, (app_id, label, *_rest) in enumerate(self.apps):
            marker = self.style.paint(">", "1;36") if index == self.selected_app_index else " "
            text, color_name = self._status_text(app_id)
            colorize = getattr(self.style, color_name)
            status = colorize(text)
            lines.append(f" {marker} {label:<36}{status}")
        lines.extend(
            (
                "",
                self.style.muted("up/down to move, enter to manage, r: refresh status, q: back"),
                self.style.muted("(destroy is not available here -- use the Bash wizard's expert menu)"),
            )
        )
        return "\n".join(lines) + "\n"

    def _render_app_menu(self) -> str:
        app_id, label, _prefix, _step_id, url_key = self.apps[self.selected_app_index]
        status_text, color_name = self._status_text(app_id)
        colorize = getattr(self.style, color_name)
        lines = [self.style.heading(label), "", f"  Status: {colorize(status_text)}"]
        url = self._current_url(url_key)
        if url:
            lines.append(f"  URL:    {url}")
        lines.append("")
        for index, (_action_id, action_label) in enumerate(_APP_ACTIONS):
            marker = self.style.paint(">", "1;36") if index == self.selected_action_index else " "
            suffix = "  (running...)" if self.running and index == self.selected_action_index else ""
            row = f" {marker} {action_label}{suffix}"
            lines.append(self.style.warn(row) if suffix else row)
        if self.show_credentials:
            lines.extend(("", "Login guidance"))
            hints = _LOGIN_HINTS.get(app_id)
            if hints:
                lines.extend(f"  {hint}" for hint in hints)
            elif url:
                lines.append("  No separate login guidance -- see the URL above.")
            else:
                lines.append("  No URL or login guidance available for this app yet.")
        lines.append("")
        lines.append(f"Mode: {self.mode_label()}")
        if self.last_execution is not None:
            state = "ran" if self.last_execution.executed else "previewed"
            outcome = "ok" if self.last_execution.ok else "failed"
            lines.append(f"Last: {self.last_execution.operation_id} ({state}, {outcome}) -- {self.last_execution.detail}")
        lines.extend(
            (
                "",
                self.style.muted("up/down to move, enter to select, a: toggle execute/dry-run, r: back, q: back"),
            )
        )
        return "\n".join(lines) + "\n"

    def _current_url(self, url_key: str) -> str:
        if not url_key or not self.env_file.exists():
            return ""
        values = ConfigStore(self.env_file).load().values()
        value = values.get(url_key, "")
        return display_value(url_key, value) if value else ""

    def handle_event(self, event: Event) -> NavigationCommand:
        if isinstance(event, TickEvent):
            result = self._poll_execution()
            if result is not None:
                self.last_execution = result
                self._refresh_statuses()
            return NavigationCommand.stay()
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if self.stage is _Stage.LIST:
            return self._handle_list(event)
        return self._handle_app_menu(event)

    def _handle_list(self, event: KeyEvent) -> NavigationCommand:
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("up", "k"):
            self.selected_app_index = (self.selected_app_index - 1) % len(self.apps)
            return NavigationCommand.stay()
        if event.key in ("down", "j"):
            self.selected_app_index = (self.selected_app_index + 1) % len(self.apps)
            return NavigationCommand.stay()
        if event.key in ("r", "R"):
            self._refresh_statuses()
            return NavigationCommand.stay()
        if event.key == "enter":
            self.stage = _Stage.APP_MENU
            self.selected_action_index = 0
            self.show_credentials = False
            self.armed = False
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _handle_app_menu(self, event: KeyEvent) -> NavigationCommand:
        if event.key in ("q", "Q"):
            return NavigationCommand.pop()
        if event.key == "escape":
            self.stage = _Stage.LIST
            return NavigationCommand.stay()
        if event.key in ("r", "R") and not self.is_executing:
            self.stage = _Stage.LIST
            return NavigationCommand.stay()
        if event.key in ("up", "k"):
            self.selected_action_index = (self.selected_action_index - 1) % len(_APP_ACTIONS)
            # Same reasoning as Bash's own single-choice-per-screen shape:
            # arming is a decision about *this* action, not session-wide.
            self.armed = False
            return NavigationCommand.stay()
        if event.key in ("down", "j"):
            self.selected_action_index = (self.selected_action_index + 1) % len(_APP_ACTIONS)
            self.armed = False
            return NavigationCommand.stay()
        if event.key in ("a", "A"):
            self.toggle_armed()
            return NavigationCommand.stay()
        if event.key == "enter":
            command = self._select_action()
            return command if command is not None else NavigationCommand.stay()
        return NavigationCommand.stay()

    def _select_action(self) -> NavigationCommand | None:
        action_id, _label = _APP_ACTIONS[self.selected_action_index]
        if action_id == "logs":
            _app_id, _label, _prefix, step_id, _url = self.apps[self.selected_app_index]
            return NavigationCommand.push(LogsScreen(initial_step_id=step_id))
        if action_id == "credentials":
            self.show_credentials = not self.show_credentials
            return None
        self._run_selected(action_id)
        return None

    def _run_selected(self, action: str) -> None:
        if self.is_executing:
            return
        app_id, _label, _prefix, _step_id, _url = self.apps[self.selected_app_index]
        executing = self.consume_arm()
        spec = self.catalog.app(app_id, action)
        if not executing:
            self.last_execution = self.runner.run(spec, execute=False)
            return
        # Real execution runs on a background thread so this screen can
        # show "running" immediately instead of freezing until a
        # Helm-backed start/stop (which can take minutes) returns -- see
        # DeployService.start_execute()/poll_execute() for the same
        # pattern. The result arrives via a TickEvent and
        # _poll_execution() above.
        with self._execution_lock:
            self.running = True
            thread = threading.Thread(target=self._execute_in_background, args=(spec,), daemon=True)
            self._running_thread = thread
        thread.start()

    def _execute_in_background(self, spec: OperationSpec) -> None:
        result = self.runner.run(spec, execute=True)
        with self._execution_lock:
            self._pending_execution = result

    def _poll_execution(self) -> OperationExecution | None:
        with self._execution_lock:
            if self._pending_execution is None:
                return None
            result = self._pending_execution
            self._pending_execution = None
            self._running_thread = None
            self.running = False
        return result
