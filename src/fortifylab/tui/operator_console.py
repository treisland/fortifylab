"""Interactive operator console for the Python CLI migration."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from collections.abc import Callable

from fortifylab.dependencies import dependency_checks, migration_status_lines

from .menu import OPERATOR_MENU, render_operator_menu
from .theme import TerminalStyle


InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]
CommandRunner = Callable[[tuple[str, ...]], int]


@dataclass(frozen=True)
class ConsoleCommand:
    label: str
    command: tuple[str, ...]
    mutating: bool = False
    note: str = ""


class OperatorConsole:
    """Small testable menu loop that routes to existing proven workflows."""

    def __init__(
        self,
        *,
        style: TerminalStyle | None = None,
        input_fn: InputFn = input,
        output_fn: OutputFn = print,
        command_runner: CommandRunner | None = None,
        dashboard_factory: Callable[[], str] | None = None,
    ) -> None:
        self.style = style or TerminalStyle.from_environment()
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.command_runner = command_runner or self._run_command
        self.dashboard_factory = dashboard_factory or self._live_dashboard

    def run(self) -> int:
        """Run until the operator quits."""

        while True:
            self.write(render_operator_menu(style=self.style, preview=False), end="")
            choice = self.prompt("Select: ").strip().lower()
            if choice in {"q", "quit", "exit"}:
                self.write("Goodbye.")
                return 0
            if choice in {"", "b", "back"}:
                continue
            if not choice.isdigit():
                self.write(self.style.fail("Invalid selection. Choose a number shown above or q to quit."))
                continue
            index = int(choice)
            if not 1 <= index <= len(OPERATOR_MENU):
                self.write(self.style.fail("Invalid selection. Choose a number shown above or q to quit."))
                continue
            self.route(OPERATOR_MENU[index - 1].key)

    def route(self, key: str) -> None:
        routes = {
            "dashboard": self.screen_dashboard,
            "deploy": self.screen_deploy,
            "applications": self.screen_applications,
            "configuration": self.screen_configuration,
            "runbooks": self.screen_runbooks,
            "logs": self.screen_logs,
            "diagnostics": self.screen_diagnostics,
            "certificates": self.screen_certificates,
            "tools": self.screen_tools,
            "help": self.screen_help,
        }
        routes[key]()

    def screen_dashboard(self) -> None:
        self.write("")
        self.write(self.dashboard_factory(), end="")
        self.pause()

    def screen_deploy(self) -> None:
        self.command_screen(
            "Deploy / Resume",
            (
                ConsoleCommand(
                    "Start or resume guided deployment",
                    ("./start_wizard.sh",),
                    mutating=True,
                    note="Hands off to the production Bash wizard.",
                ),
            ),
        )

    def screen_applications(self) -> None:
        self.command_screen(
            "Applications",
            (
                ConsoleCommand("Start SSC", ("./apps/ssc/start.sh",), mutating=True),
                ConsoleCommand("Stop SSC", ("./apps/ssc/stop.sh",), mutating=True),
                ConsoleCommand("Start LIM", ("./apps/lim/start.sh",), mutating=True),
                ConsoleCommand("Stop LIM", ("./apps/lim/stop.sh",), mutating=True),
            ),
        )

    def screen_configuration(self) -> None:
        self.command_screen(
            "Configuration",
            (
                ConsoleCommand("Show configuration diagnostics", ("./bin/fortifylab", "config", "diagnostics")),
                ConsoleCommand("Validate configuration", ("./bin/fortifylab", "config", "validate")),
                ConsoleCommand(
                    "Preview derived URL repair",
                    ("./bin/fortifylab", "config", "repair-derived", "--dry-run"),
                ),
            ),
        )

    def screen_runbooks(self) -> None:
        self.command_screen(
            "Runbooks",
            (
                ConsoleCommand("Preview first-scan runbook", ("./bin/fortifylab", "runbook", "--preview", "first-scan")),
                ConsoleCommand(
                    "Open guided wizard for interactive runbooks",
                    ("./start_wizard.sh",),
                    mutating=True,
                    note="Choose Runbooks from the Bash wizard menu.",
                ),
            ),
        )

    def screen_logs(self) -> None:
        self.command_screen(
            "Logs",
            (
                ConsoleCommand("Recent SSC logs", ("./bin/fortifylab", "logs", "--pod", "ssc-webapp-0")),
                ConsoleCommand("Follow SSC logs", ("./bin/fortifylab", "logs", "--pod", "ssc-webapp-0", "--follow")),
            ),
        )

    def screen_diagnostics(self) -> None:
        self.command_screen(
            "Diagnostics",
            (
                ConsoleCommand("Run read-only collector checks", ("./bin/fortifylab", "doctor", "--collect")),
                ConsoleCommand(
                    "Create sanitized diagnostics bundle",
                    ("./bin/fortifylab", "doctor", "--bundle-dir", ".fortifylab/diagnostics"),
                ),
            ),
        )

    def screen_certificates(self) -> None:
        self.command_screen(
            "Certificates & Trust",
            (
                ConsoleCommand("Generate TLS certificates", ("./scripts/create-certs.sh",), mutating=True),
                ConsoleCommand("Configure fcli trust for lab TLS", ("./runbooks/official/fcli/configure-lab-trust.sh",)),
            ),
        )

    def screen_tools(self) -> None:
        self.write("")
        self.write(self.style.heading("Tools"))
        for line in migration_status_lines():
            self.write(line)
        self.write("")
        self.write("Optional dependencies:")
        for check in dependency_checks():
            self.write(f"  {check.name:<10} {check.state:<9} {check.purpose}")
        self.pause()

    def screen_help(self) -> None:
        self.write("")
        self.write(self.style.heading("Help"))
        self.write("Use the numbered workspaces to inspect the lab and launch existing operational flows.")
        self.write("Mutating deployment actions ask for confirmation before handing off to Bash scripts.")
        self.write("The Bash wizard remains authoritative for deployment changes while Python screens mature.")
        self.write("Web UI work is out of active scope; use Kubernetes-native tools for full cluster UI needs.")
        self.pause()

    def command_screen(self, title: str, commands: tuple[ConsoleCommand, ...]) -> None:
        while True:
            self.write("")
            self.write(self.style.heading(title))
            for index, command in enumerate(commands, start=1):
                marker = "mutation" if command.mutating else "read-only"
                self.write(f"  {index}. {command.label} [{marker}]")
                if command.note:
                    self.write(f"     {self.style.muted(command.note)}")
            self.write("  b. Back")
            choice = self.prompt("Select: ").strip().lower()
            if choice in {"b", "back", "q", "quit"}:
                return
            if not choice.isdigit() or not 1 <= int(choice) <= len(commands):
                self.write(self.style.fail("Invalid selection. Choose a number shown above or b to go back."))
                continue
            self.execute(commands[int(choice) - 1])
            self.pause()

    def execute(self, command: ConsoleCommand) -> int:
        self.write("")
        self.write(f"Action: {command.label}")
        self.write(f"Command: {' '.join(command.command)}")
        if command.mutating:
            answer = self.prompt("Run this action now? [y/N]: ").strip().lower()
            if answer not in {"y", "yes"}:
                self.write("Skipped.")
                return 0
        rc = self.command_runner(command.command)
        if rc == 0:
            self.write(self.style.ok("Action completed."))
        else:
            self.write(self.style.fail(f"Action failed with exit code {rc}."))
        return rc

    def pause(self) -> None:
        self.prompt("Press Enter to continue...")

    def prompt(self, prompt: str) -> str:
        return self.input_fn(prompt)

    def write(self, text: str = "", *, end: str = "\n") -> None:
        if end == "\n":
            self.output_fn(text)
        else:
            self.output_fn(text + end)

    @staticmethod
    def _run_command(command: tuple[str, ...]) -> int:
        return subprocess.call(command)

    @staticmethod
    def _live_dashboard() -> str:
        from fortifylab.dashboard import collect_dashboard, render_dashboard

        return render_dashboard(collect_dashboard())
