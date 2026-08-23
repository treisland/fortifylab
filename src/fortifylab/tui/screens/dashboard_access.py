"""Kubernetes Dashboard access screen -- the interactive replacement for
the ephemeral-token half of ``dashboard_access_menu()`` in
``scripts/wizard/operations.sh``.

Only the two 1-hour tokens are wired (view-only: no confirmation needed,
matching Bash; administrator: gated by arming, matching Bash's plain y/N
confirm for that option). Persistent tokens need a typed ``PERSISTENT``
confirmation in Bash and stay out of scope until the TUI has real
text-entry, same rationale as destroy in ``ApplicationsScreen``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fortifylab.config.store import ConfigStore
from fortifylab.services.dashboard_access_service import DashboardAccessService

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import Armable, NavigationCommand, Screen

_ADMIN_WARNING = (
    "WARNING: administrator access can modify or delete every workload, Secret, "
    "and persistent resource in this cluster."
)


@dataclass
class DashboardAccessScreen(Armable, Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: DashboardAccessService = field(default_factory=DashboardAccessService)
    env_file: Path = field(default_factory=lambda: Path(".env"))
    message: str | None = None

    def render(self) -> str:
        domain = ConfigStore(self.env_file).load().values().get("DOMAIN", "<unset>") if self.env_file.exists() else "<unset>"
        lines = [
            self.style.heading("Kubernetes Dashboard access"),
            "",
            f"URL: https://dashboard.{domain}",
            "",
            "One-hour tokens are recommended. Persistent tokens (Bash-wizard-only,",
            "needs a typed confirmation this TUI doesn't have yet) remain valid",
            "until revoked or their service account is removed.",
            "",
            "  v: generate 1-hour view-only token",
            "  m: generate 1-hour administrator token (requires arming with 'a')",
        ]
        lines.append("")
        lines.append(f"Mode: {self.mode_label(armed_text='armed', dry_run_text='not armed')}")
        if not self.armed:
            lines.append(self.style.muted(_ADMIN_WARNING))
        if self.message is not None:
            lines.extend(("", self.message))
        lines.extend(("", self.style.muted("v: view-only token, a: arm, m: admin token, q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("a", "A"):
            self.toggle_armed()
            return NavigationCommand.stay()
        if event.key in ("v", "V"):
            # Viewer tokens never need arming (matching Bash's no-confirm
            # behavior for this option), but generating one is an
            # unrelated action from whatever "m" arming was for -- disarm
            # so a stale arm can't silently carry over into a later "m".
            self.armed = False
            self._generate("viewer")
            return NavigationCommand.stay()
        if event.key in ("m", "M"):
            self._generate("admin")
            return NavigationCommand.stay()
        return NavigationCommand.stay()

    def _generate(self, access: str) -> None:
        if access == "admin" and not self.consume_arm():
            self.message = self.style.fail("Press a to arm, then m again to generate an administrator token.")
            return
        if not self.service.resources_ready():
            self.message = self.style.fail(
                "Dashboard access resources are missing or incomplete. "
                "Deploy or repair the Dashboard via the Bash wizard first."
            )
            return
        result = self.service.create_admin_token() if access == "admin" else self.service.create_viewer_token()
        label = "administrator" if access == "admin" else "view-only"
        if result.ok:
            self.message = f"{label.title()} token (expires in 1 hour):\n{result.stdout.strip()}"
        else:
            self.message = self.style.fail(result.stderr or result.stdout or f"Could not generate the {label} token.")
