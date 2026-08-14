"""Stdlib web console app for local/LAN Fortify Lab previews."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from fortifylab.diagnostics import route_findings
from fortifylab.operations import OperationCatalog
from fortifylab.status import LiveStatusPoller


@dataclass(frozen=True)
class WebConsoleConfig:
    bind_host: str = "127.0.0.1"
    port: int = 8765
    access_token: str | None = None
    allow_lan: bool = False

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        if self.allow_lan and not self.access_token:
            issues.append("LAN access requires an access token.")
        if self.bind_host not in ("127.0.0.1", "localhost") and not self.allow_lan:
            issues.append("Non-local bind requires allow_lan=True.")
        return tuple(issues)


class WebConsoleApp:
    def __init__(self, config: WebConsoleConfig, static_dir: Path | None = None) -> None:
        self.config = config
        self.static_dir = static_dir or Path(__file__).with_name("static")

    def is_local_only(self) -> bool:
        return self.config.bind_host in ("127.0.0.1", "localhost")

    def authorize(self, token: str | None) -> bool:
        return self.authorize_request(token)

    def authorize_request(self, token: str | None) -> bool:
        if not self.config.access_token:
            return self.is_local_only()
        return token == self.config.access_token

    def api_response(self, path: str) -> tuple[int, dict[str, Any]]:
        if path == "/api/status":
            operations = OperationCatalog().list()
            return 200, {
                "mode": "lab",
                "operations": [
                    {"id": spec.operation_id, "kind": spec.kind.value, "impact": spec.impact.value}
                    for spec in operations
                ],
            }
        if path == "/api/deployment/status":
            return 200, LiveStatusPoller().snapshot().to_dict()
        if path == "/api/routes":
            return 200, {"findings": list(route_findings(()))}
        if path == "/api/config":
            return 200, {"sections": ["identity", "urls", "versions", "credentials"], "secrets_redacted": True}
        if path == "/api/certificates":
            return 200, {"root_ca": "certs/rootCA.pem", "private_key_exported": False}
        return 404, {"error": "not found"}

    def api_envelope(self, path: str) -> tuple[int, dict[str, Any]]:
        status, body = self.api_response(path)
        if status >= 400:
            code = str(body.get("error", "not_found"))
            return status, self.error_envelope(code, "API endpoint not found.")
        return status, {"ok": True, "data": body, "error": None}

    def error_envelope(self, code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "data": None, "error": {"code": code, "message": message}}

    def static_asset(self, relative: str) -> tuple[str, str]:
        safe = relative.lstrip("/") or "index.html"
        if ".." in safe:
            raise FileNotFoundError(safe)
        path = self.static_dir / safe
        if not path.is_file():
            raise FileNotFoundError(safe)
        content_type = "text/html" if path.suffix == ".html" else "text/css" if path.suffix == ".css" else "application/javascript"
        return content_type, path.read_text(encoding="utf-8")

    def json_response(self, path: str) -> str:
        status, body = self.api_response(path)
        return json.dumps({"status": status, "body": body}, indent=2)
