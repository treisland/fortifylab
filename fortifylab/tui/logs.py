"""Read-only log workflow screen contracts for the Python TUI."""

from __future__ import annotations

from collections.abc import Iterable

from fortifylab.logging import DEFAULT_LOG_TAIL_LINES, LogReadResult, LogSource, discover_log_sources, read_log_tail
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


class LogsWorkflowScreen(WorkflowScreen):
    """Pure TUI model for read-only log source listing and preview."""

    def __init__(self, log_sources: Iterable[LogSource] | None = None) -> None:
        super().__init__("logs", "Logs", "Read-only log sources. Missing logs show a clear unavailable state.")
        self._sources = tuple(log_sources) if log_sources is not None else discover_log_sources()
        self.selected_index = 0
        self.last_read: LogReadResult | None = None

    @property
    def selected_source(self) -> LogSource | None:
        if not self._sources:
            return None
        return self._sources[self.selected_index]

    def render(self) -> str:
        lines = [self.summary, "Use Up/Down or number keys to select. r refreshes the selected log tail, b backs out.", "Sources:"]
        if not self._sources:
            lines.append("SKIP no log sources are known.")
        for index, source in enumerate(self._sources, start=1):
            marker = ">" if index - 1 == self.selected_index else " "
            path = str(source.path) if source.path is not None else "<unresolved>"
            lines.append(f"{marker} {index}. {source.label} [{source.availability}] {path}")
            if source.detail:
                lines.append(f"    {source.detail}")
        if self.last_read is not None:
            lines.append("")
            lines.append(self.last_read.message)
            if self.last_read.lines:
                lines.append("Tail:")
                lines.extend(f"  {line}" for line in self.last_read.lines)
            elif self.last_read.source.availability != "available":
                lines.append(f"{self.last_read.source.label}: {self.last_read.source.availability}")
        return "\n".join(lines)

    @property
    def current_view(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def refresh(self) -> str:
        source = self.selected_source
        if source is None:
            self.last_read = None
            return self.render()
        self.last_read = read_log_tail(source, lines=DEFAULT_LOG_TAIL_LINES)
        return self.render()

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"back", "b", "escape", ""}:
            return WorkflowKeyResult("Back to menu.", exit_screen=True)
        if key in {"up", "down"}:
            self._move_selection(-1 if key == "up" else 1)
            selected = self.selected_source
            return WorkflowKeyResult(f"Selected {selected.label}." if selected else "No log sources are known.")
        if key.isdigit() and key != "0":
            index = int(key) - 1
            if index < len(self._sources):
                self.selected_index = index
                return WorkflowKeyResult(f"Selected {self._sources[index].label}.")
        if key in {"r", "enter"}:
            self.refresh()
            selected = self.selected_source
            return WorkflowKeyResult(f"Refreshed {selected.label}." if selected else "No log sources are known.")
        return WorkflowKeyResult(f"No logs workflow action is bound to {key!r}.")

    on_key = handle_key

    def _move_selection(self, offset: int) -> None:
        if not self._sources:
            self.selected_index = 0
            return
        self.selected_index = (self.selected_index + offset) % len(self._sources)


class WizardLogWorkflowScreen(LogsWorkflowScreen):
    """Focused workflow screen for the legacy wizard log source."""

    def __init__(self, log_sources: Iterable[LogSource] | None = None) -> None:
        sources = tuple(log_sources) if log_sources is not None else discover_log_sources()
        wizard_sources = tuple(source for source in sources if source.id == "wizard_log")
        super().__init__(wizard_sources)
        self.id = "wizard_log"
        self.title = "Wizard log"
        self.summary = "Read-only wizard log tail. Missing logs show a clear unavailable state."


def build_logs_workflow(log_sources: Iterable[LogSource] | None = None) -> LogsWorkflowScreen:
    return LogsWorkflowScreen(log_sources=log_sources)


def build_wizard_log_workflow(log_sources: Iterable[LogSource] | None = None) -> WizardLogWorkflowScreen:
    return WizardLogWorkflowScreen(log_sources=log_sources)
