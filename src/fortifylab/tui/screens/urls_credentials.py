"""URLs & Credentials screen -- the interactive replacement for
``urls_creds()`` in ``scripts/wizard/operations.sh``.

Entirely read-only: service URLs and login guidance come from the current
``.env`` (redacted the same way ``ConfigurationScreen`` already redacts
every ``.env`` value), retrieval commands and SSC guidance are static
text, and credential *availability* (present/unavailable, never the value
itself) is an opt-in check via ``UrlsCredentialsService``.

Not wired: revealing an actual credential value. Bash's
``credential_reveal_once`` requires typing the literal word ``REVEAL``
first -- the same typed-confirmation blocker as destroy, and there is no
text-entry widget in the TUI to gate that with the same care.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fortifylab.config.envfile import display_value
from fortifylab.config.store import ConfigStore
from fortifylab.services.urls_credentials_service import CredentialCheck, UrlsCredentialsService

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


@dataclass
class UrlsCredentialsScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    service: UrlsCredentialsService = field(default_factory=UrlsCredentialsService)
    env_file: Path = field(default_factory=lambda: Path(".env"))
    availability: tuple[tuple[CredentialCheck, bool], ...] | None = None

    def _env_values(self) -> dict[str, str]:
        if not self.env_file.exists():
            return {}
        return ConfigStore(self.env_file).load().values()

    def render(self) -> str:
        values = self._env_values()
        domain = display_value("DOMAIN", values.get("DOMAIN", "<unset>"))
        lines = [self.style.heading("URLs & Credentials"), "", "Service URLs"]
        for label, key in (
            ("SSC", "SSC_URL"),
            ("LIM", "LIM_URL"),
            ("SAST controller", "SCSAST_CTRL_URL"),
            ("DAST", "SCDAST_URL"),
        ):
            lines.append(f"  {label:<16} {display_value(key, values.get(key, '<unset>'))}")
        lines.append(f"  {'Dashboard':<16} https://dashboard.{domain}")

        lines.extend(
            (
                "",
                "Login guidance",
                "  SSC              admin / refer to the SSC documentation for the default password",
                "  LIM              lim_admin / stored in lim-admin-credentials",
                "  DAST             SSC user mapped to a DAST role",
                "  Dashboard        generate a token from Kubernetes Dashboard access",
                "",
                "Credential availability",
            )
        )
        if self.availability is None:
            lines.append(self.style.muted("  press c to check (read-only; never shows the value)"))
        else:
            for check, present in self.availability:
                marker = self.style.ok("available") if present else self.style.muted("unavailable")
                lines.append(f"  {check.label:<36} {marker}")

        lines.extend(("", self.style.muted("c: check credential availability, q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        if event.key in ("c", "C"):
            self.availability = self.service.check_availability()
            return NavigationCommand.stay()
        return NavigationCommand.stay()
