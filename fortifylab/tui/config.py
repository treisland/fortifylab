"""Configuration Editor workflow screen for the Python TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fortifylab.config import ConfigValidationError, EnvDocument, repair_domain_changes, validate_env_file, write_env_file
from fortifylab.config.cli import diagnostics_command, validate_command
from fortifylab.paths import repo_root
from fortifylab.tui.workflows import WorkflowKeyResult, WorkflowScreen


def _default_env_file() -> Path:
    return repo_root() / ".env"


@dataclass
class ConfigEditorScreen(WorkflowScreen):
    """Pure workflow model for config diagnostics, validation, and repair."""

    def __init__(self, env_file: Path | str | None = None) -> None:
        super().__init__(
            "configuration_editor",
            "Configuration Editor",
            "Configuration workflow: diagnostics, validation, redacted derived repair preview, and confirmation-gated repair.",
        )
        self.env_file = Path(env_file) if env_file is not None else _default_env_file()
        self._view = "overview"
        self._last_output = ""
        self._repair_pending = False

    def diagnostics(self) -> str:
        output, _status = _capture_config_command(diagnostics_command, self.env_file)
        self._view = "diagnostics"
        self._last_output = output
        self._repair_pending = False
        return self.render()

    def validate(self) -> str:
        output, _status = _capture_config_command(validate_command, self.env_file)
        self._view = "validation"
        self._last_output = output
        self._repair_pending = False
        return self.render()

    def preview_repair(self) -> str:
        missing = self._missing_file_message()
        if missing is not None:
            self._view = "repair_preview"
            self._last_output = missing
            self._repair_pending = False
            return self.render()

        changes = repair_domain_changes(self.env_file)
        diff = EnvDocument.read(self.env_file).diff(changes)
        lines = [f"Derived config repair preview: {self.env_file}"]
        if not diff:
            lines.append("No derived config changes needed.")
            self._repair_pending = False
        else:
            lines.append("Planned changes:")
            lines.extend(f"- {entry.render()}" for entry in diff)
            lines.append("Press y to apply these repairs. Any write creates a backup and rollback marker.")
            self._repair_pending = True
        lines.append("Preview only: no changes written.")
        self._view = "repair_preview"
        self._last_output = "\n".join(lines)
        return self.render()

    preview = preview_repair
    repair_preview = preview_repair

    def apply_repair(self, *, confirmed: bool = False) -> str:
        if not confirmed:
            self._view = "repair_result"
            self._last_output = "Repair not applied: explicit confirmation is required."
            self._repair_pending = False
            return self.render()

        missing = self._missing_file_message()
        if missing is not None:
            self._view = "repair_result"
            self._last_output = missing
            self._repair_pending = False
            return self.render()

        changes = repair_domain_changes(self.env_file)
        diff = EnvDocument.read(self.env_file).diff(changes)
        if not diff:
            self._view = "repair_result"
            self._last_output = f"Derived config repair: {self.env_file}\nNo derived config changes needed."
            self._repair_pending = False
            return self.render()

        try:
            result = write_env_file(self.env_file, changes, reason="config-repair-derived")
        except ConfigValidationError as exc:
            lines = ["Repair would leave configuration invalid; no changes written."]
            for issue in exc.issues:
                value = f" ({issue.display_value})" if issue.value is not None else ""
                lines.append(f"- {issue.key}: {issue.message}{value}")
            self._last_output = "\n".join(lines)
        else:
            lines = [
                f"Applied {len(result.changed_keys)} changes: {', '.join(result.changed_keys)}",
            ]
            if result.backup is not None:
                lines.append(f"Backup: {result.backup.backup_path}")
                lines.append(f"Rollback marker: {result.backup.rollback_marker}")
            self._last_output = "\n".join(lines)
        self._view = "repair_result"
        self._repair_pending = False
        return self.render()

    def back(self) -> str:
        self._view = "overview"
        self._last_output = ""
        self._repair_pending = False
        return self.render()

    go_back = back
    return_to_overview = back

    @property
    def current_screen(self) -> str:
        return self.render()

    @property
    def screen(self) -> str:
        return self.render()

    def render(self) -> str:
        lines = [self.summary, f"Env file: {self.env_file}", ""]
        if self._last_output:
            lines.append(_bounded_output(self._last_output))
            lines.append("")
        lines.extend(
            (
                "Actions:",
                "d  Diagnostics",
                "v  Validate",
                "p  Preview derived repair",
                "y  Apply previewed repair (confirmation required)",
                "b  Back to menu",
            )
        )
        if self._repair_pending:
            lines.append("")
            lines.append("Confirmation pending: press y to apply the previewed derived repair.")
        return "\n".join(lines)

    def handle_key(self, key: str) -> WorkflowKeyResult:
        if key in {"back", "b", "escape", "r", ""}:
            return WorkflowKeyResult("Returned to menu.", exit_screen=True)
        if key == "d":
            self.diagnostics()
            return WorkflowKeyResult("Rendered config diagnostics.")
        if key == "v":
            self.validate()
            issues = validate_env_file(self.env_file) if self.env_file.is_file() else ()
            return WorkflowKeyResult("Config validation is valid." if not issues else "Config validation has findings.")
        if key == "p":
            self.preview_repair()
            return WorkflowKeyResult("Rendered derived repair preview.")
        if key == "y":
            if not self._repair_pending:
                self.apply_repair(confirmed=False)
                return WorkflowKeyResult("Preview the derived repair before applying it.")
            self.apply_repair(confirmed=True)
            return WorkflowKeyResult("Applied derived repair with backup, or reported why no write occurred.")
        return WorkflowKeyResult(f"No config workflow action is bound to {key!r}.")

    def _missing_file_message(self) -> str | None:
        if self.env_file.is_file():
            return None
        return f"Config file not found: {self.env_file}"


def build_config_workflow(env_file: Path | str | None = None) -> ConfigEditorScreen:
    return ConfigEditorScreen(env_file=env_file)


def _capture_config_command(command, env_file: Path) -> tuple[str, int]:  # type: ignore[no-untyped-def]
    lines: list[str] = []
    status = command(env_file, print_line=lines.append)
    return "\n".join(lines), status


def _bounded_output(text: str, *, limit: int = 80) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    hidden = len(lines) - limit
    return "\n".join([*lines[:limit], f"... {hidden} more lines"])
