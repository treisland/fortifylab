"""Flight Plans screen -- the interactive replacement for the Flight Plan
preview half of `versions_menu()` in `scripts/wizard/menu.sh`.

Read-only: lists Flight Plans and shows a plan's components compared
against the current `.env`. Promoting a candidate, applying a plan (writes
`.env`), and Docker Hub discovery all stay Bash/`scripts/tools/flight-plans.py`-only
for now -- same rationale as `ConfigurationScreen` skipping free-text edits:
those are real writes, and this screen has no text-entry widget to gate
them with the care the Bash flow already takes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from fortifylab.domain.flight_plans import Catalog, default_catalog_path, merged_read_catalog
from fortifylab.services.flight_plan_service import FlightPlanService

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


@dataclass
class FlightPlansScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: FlightPlanService | None = None
    env_file: Path = field(default_factory=lambda: Path(".env"))
    selected_index: int = 0
    viewing: bool = False
    load_error: str | None = None

    def __post_init__(self) -> None:
        if self.service is not None:
            return
        try:
            self.service = FlightPlanService(merged_read_catalog(default_catalog_path()))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            self.load_error = f"Could not load the Flight Plan catalog: {exc}"
            self.service = FlightPlanService(Catalog(path=default_catalog_path(), data={}))

    def render(self) -> str:
        if self.load_error:
            lines = [self.style.heading("Flight Plans"), "", self.style.fail(self.load_error), "", self.style.muted("q: back")]
            return "\n".join(lines) + "\n"
        if self.viewing:
            return self._render_detail()
        return self._render_list()

    def _render_list(self) -> str:
        assert self.service is not None
        plans = self.service.plans()
        lines = [self.style.heading("Flight Plans"), ""]
        if not plans:
            lines.append(self.style.muted("No Flight Plans in the catalog."))
        default_id = self.service.catalog.default_flight_plan
        for index, plan in enumerate(plans):
            marker = self.style.paint(">", "1;36") if index == self.selected_index else " "
            default_tag = " (default)" if plan.plan_id == default_id else ""
            lines.append(f" {marker} {plan.label:<28} {plan.status:<12} family={plan.family}{default_tag}")
        lines.extend(("", self.style.muted("up/down to move, enter to view, q: back")))
        return "\n".join(lines) + "\n"

    def _render_detail(self) -> str:
        assert self.service is not None
        plan = self.service.plans()[self.selected_index]
        lines = [self.style.heading(f"Flight Plan -- {plan.label}"), "", f"Status: {plan.status}   Family: {plan.family}"]
        if plan.notes:
            lines.append(f"Notes:  {plan.notes}")
        lines.extend(("", "Components"))
        for key, value in plan.components.items():
            lines.append(f"  {key:<32} {value or '<review required>'}")
        lines.extend(("", "Compared against the current .env"))
        comparison = self.service.compare_env(plan.plan_id, self.env_file)
        for field_ in comparison.fields:
            if field_.separate:
                label, paint = "database-separate", self.style.muted
            elif field_.review_required:
                label, paint = "review required", self.style.muted
            elif field_.aligned:
                label, paint = "aligned", self.style.ok
            else:
                label, paint = "drifted", self.style.fail
            # Pad the plain label before wrapping it in ANSI color codes --
            # padding a colored string counts the escape-sequence bytes
            # toward the width too, throwing off column alignment.
            state = paint(f"{label:<16}")
            lines.append(f"  {field_.key:<32} {state} expected={field_.expected}  current={field_.current}")
        lines.extend(("", self.style.muted("b: back to list, q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if self.load_error:
            return NavigationCommand.stay()
        assert self.service is not None
        plans = self.service.plans()
        if not plans:
            return NavigationCommand.stay()
        if self.viewing:
            if event.key in ("b", "B"):
                self.viewing = False
            return NavigationCommand.stay()
        if event.key in ("up", "k"):
            self.selected_index = (self.selected_index - 1) % len(plans)
        elif event.key in ("down", "j"):
            self.selected_index = (self.selected_index + 1) % len(plans)
        elif event.key == "enter":
            self.viewing = True
        return NavigationCommand.stay()
