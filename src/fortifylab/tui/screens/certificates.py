"""Certificates & Trust screen -- the interactive replacement for
``certificate_trust_handoff()`` in ``scripts/wizard/operations.sh``.

Entirely read-only and static: the root CA path (from ``.env``, falling
back to the same ``$FORTIFY_CERTS/rootCA.pem`` default Bash uses) and the
lab hostnames a client needs to trust that CA for. Never reads, displays,
or checks the private key (``ROOTCA_KEY``) or any workload TLS material.

Not wired: the broader "TLS certificates and trust" submenu in
``scripts/wizard/setup.sh`` -- generating/regenerating lab TLS artifacts,
bringing your own certificate and key, staging a root CA export, and
staging fcli trust configuration. Those are mutating or file-writing
operations with no equivalent screen yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fortifylab.config.store import ConfigStore

from ..events import Event, KeyEvent
from ..theme import TerminalStyle
from .base import NavigationCommand, Screen


@dataclass
class CertificatesScreen(Screen):
    style: TerminalStyle = field(default_factory=TerminalStyle.from_environment)
    env_file: Path = field(default_factory=lambda: Path(".env"))

    def _env_values(self) -> dict[str, str]:
        if not self.env_file.exists():
            return {}
        return ConfigStore(self.env_file).load().values()

    def render(self) -> str:
        values = self._env_values()
        domain = values.get("DOMAIN", "<unset>")
        # Bash: ${ROOTCA_CERT:-$FORTIFY_CERTS/rootCA.pem} -- an unset
        # FORTIFY_CERTS expands to the empty string there, not a
        # placeholder, so mirror that with a plain "" default rather than
        # comparing against the "<unset>" display sentinel.
        fortify_certs = values.get("FORTIFY_CERTS", "")
        root_ca = values.get("ROOTCA_CERT") or f"{fortify_certs}/rootCA.pem"
        namespace = values.get("NAMESPACE", "fortify")

        lines = [
            self.style.heading("Certificates & Trust"),
            "",
            "mkcert root CA",
            f"  {root_ca}",
            "",
            "Import the mkcert root CA into each client machine or browser trust",
            "store that will access the lab URLs. FortifyLab serves workload TLS",
            f"from the Kubernetes Secret {namespace}/tls and configures MicroK8s",
            "ingress to use it as the default certificate when the installed",
            "ingress addon supports that.",
            "",
            "Lab hostnames",
        ]
        for prefix in ("ssc", "lim", "sast", "dast", "dashboard"):
            lines.append(f"  {prefix}.{domain}")

        lines.extend(("", self.style.muted("q: back")))
        return "\n".join(lines) + "\n"

    def handle_event(self, event: Event) -> NavigationCommand:
        if not isinstance(event, KeyEvent):
            return NavigationCommand.stay()
        if event.key in ("q", "Q", "escape"):
            return NavigationCommand.pop()
        return NavigationCommand.stay()
