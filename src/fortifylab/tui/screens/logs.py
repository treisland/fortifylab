"""Logs screen -- the interactive replacement for ``stream_logs()``/
``logs_menu()`` in ``scripts/wizard/menu.sh``.

The Bash flow lists pods, filters by prefix, and only prompts when more
than one pod matches -- no free-text pod name entry, which matters since
the TUI has no text-input widget yet. This screen follows the same shape:
pick a known app/log scope, then either it auto-selects the one matching
pod or shows the matches to arrow-select.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from fortifylab.config.store import ConfigStore
from fortifylab.services.logs_service import LogsService
from fortifylab.tui.profiles import LOG_SCOPES, STEP_LABELS

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen

_SCOPES: tuple[tuple[str, str, str], ...] = tuple(
    (step_id, STEP_LABELS.get(step_id, step_id), prefix) for step_id, prefix in LOG_SCOPES.items()
)


class _Stage(str, Enum):
    SCOPES = "scopes"
    PODS = "pods"
    OUTPUT = "output"


@dataclass
class LogsScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: LogsService = field(default_factory=LogsService)
    env_file: Path = field(default_factory=lambda: Path(".env"))
    scopes: tuple[tuple[str, str, str], ...] = _SCOPES
    stage: _Stage = _Stage.SCOPES
    selected_scope_index: int = 0
    pods: tuple[str, ...] = ()
    selected_pod_index: int = 0
    output: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        # Bash reads $NAMESPACE dynamically everywhere (guided.sh,
        # operations.sh); LogsService/OperationCatalog default to the same
        # "fortify" Bash itself falls back to, but a lab with a
        # non-default NAMESPACE in .env would otherwise silently query
        # the wrong namespace for both pod listing and log tailing. Apply
        # it here so every other screen's construction pattern (read a
        # fixed set of keys from .env) stays the one place namespace
        # comes from.
        if self.env_file.exists():
            namespace = ConfigStore(self.env_file).load().values().get("NAMESPACE")
            if namespace:
                self.service.namespace = namespace

    def render(self) -> str:
        if self.stage is _Stage.SCOPES:
            return self._render_scopes()
        if self.stage is _Stage.PODS:
            return self._render_pods()
        return self._render_output()

    def _render_scopes(self) -> str:
        lines = [self.style.heading("Logs"), "", "Choose a component:"]
        for index, (_step_id, label, prefix) in enumerate(self.scopes):
            marker = self.style.paint(">", "1;36") if index == self.selected_scope_index else " "
            lines.append(f" {marker} {label:<32} {self.style.muted(prefix)}")
        if self.message:
            lines.extend(("", self.message))
        lines.extend(("", self.style.muted("up/down to move, enter to look up pods, q: back")))
        return "\n".join(lines) + "\n"

    def _render_pods(self) -> str:
        lines = [self.style.heading("Logs -- choose a pod"), ""]
        for index, pod in enumerate(self.pods):
            marker = self.style.paint(">", "1;36") if index == self.selected_pod_index else " "
            lines.append(f" {marker} {pod}")
        lines.extend(("", self.style.muted("up/down to move, enter to tail, b: back, q: back")))
        return "\n".join(lines) + "\n"

    def _render_output(self) -> str:
        lines = [self.style.heading("Logs -- output"), ""]
        lines.append(self.output or "")
        lines.extend(("", self.style.muted("r: refresh, b: back, q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if self.stage is _Stage.SCOPES:
            return self._handle_scopes(event)
        if self.stage is _Stage.PODS:
            return self._handle_pods(event)
        return self._handle_output(event)

    def _handle_scopes(self, event: KeyEvent) -> NavigationCommand:
        if event.key in ("up", "k"):
            self.selected_scope_index = (self.selected_scope_index - 1) % len(self.scopes)
        elif event.key in ("down", "j"):
            self.selected_scope_index = (self.selected_scope_index + 1) % len(self.scopes)
        elif event.key == "enter":
            self._look_up_pods()
        return NavigationCommand.stay()

    def _handle_pods(self, event: KeyEvent) -> NavigationCommand:
        if event.key in ("up", "k"):
            self.selected_pod_index = (self.selected_pod_index - 1) % len(self.pods)
        elif event.key in ("down", "j"):
            self.selected_pod_index = (self.selected_pod_index + 1) % len(self.pods)
        elif event.key == "enter":
            self._tail_selected_pod()
        elif event.key in ("b", "B"):
            self.stage = _Stage.SCOPES
        return NavigationCommand.stay()

    def _handle_output(self, event: KeyEvent) -> NavigationCommand:
        if event.key in ("r", "R"):
            self._tail_selected_pod()
        elif event.key in ("b", "B"):
            self.stage = _Stage.PODS if self.pods else _Stage.SCOPES
        return NavigationCommand.stay()

    def _look_up_pods(self) -> None:
        _step_id, _label, prefix = self.scopes[self.selected_scope_index]
        # LOG_SCOPES values are Bash glob patterns (e.g. "ssc-webapp*"), but
        # matching_pods() does a plain str.startswith() -- strip the glob
        # suffix so the literal "*" doesn't defeat every match. Some scopes'
        # prefixes overlap once stripped (sast_sensor's "scancentral-sast"
        # is itself a prefix of sast_controller's pods, and dast_scanner's
        # "sdast" is a prefix of dast_core's pods), so pass every other
        # scope's stripped prefix along to exclude those sibling pods.
        stripped_prefix = prefix.rstrip("*")
        sibling_prefixes = tuple(other.rstrip("*") for _s, _l, other in self.scopes)
        matches = self.service.matching_pods_for_scope(stripped_prefix, sibling_prefixes)
        if not matches:
            self.message = self.style.fail(f"No pods found matching '{prefix}'.")
            return
        self.message = None
        self.pods = matches
        self.selected_pod_index = 0
        if len(matches) == 1:
            self._tail_selected_pod()
        else:
            self.stage = _Stage.PODS

    def _tail_selected_pod(self) -> None:
        pod = self.pods[self.selected_pod_index]
        execution = self.service.tail(pod)
        self.output = f"$ {' '.join(execution.command)}\n\n{execution.detail}"
        self.stage = _Stage.OUTPUT
