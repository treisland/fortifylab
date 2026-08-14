"""Read-only support payload helpers for the web console."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import ssl
import tempfile
from typing import Any

from fortifylab.config.envfile import parse_env_text
from fortifylab.core.command import CommandResult, run_command
from fortifylab.status import LiveDeploymentSnapshot, RouteSummary


Runner = Callable[[tuple[str, ...]], CommandResult]

LAB_HOST_KEYS = ("SSC", "LIM", "SCSAST", "SCDAST")


@dataclass(frozen=True)
class SupportInspector:
    namespace: str = "fortify"
    kubectl: tuple[str, ...] = ("microk8s", "kubectl")
    runner: Runner | None = None
    env_file: Path = Path(".env")

    def certificate_payload(self, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        warnings: list[str] = []
        secrets = self._json_command((*self.kubectl, "-n", self.namespace, "get", "secrets", "-o", "json"), warnings)
        ingress_pods = self._json_command((*self.kubectl, "-n", "ingress", "get", "pods", "-o", "json"), warnings)
        snapshot_routes = _snapshot_routes(snapshot)
        routes = sorted({route.host for route in snapshot_routes if route.host})
        ingress_tls_secrets = sorted({route.tls_secret for route in snapshot_routes if route.tls_secret})
        inventory = self._certificate_inventory(secrets, ingress_tls_secrets)
        return {
            "root_ca": "certs/rootCA.pem",
            "private_key_exported": False,
            "namespace": self.namespace,
            "inventory": inventory,
            "ingress_tls_secrets": ingress_tls_secrets,
            "route_hosts": routes,
            "traefik_default_certificate": self._traefik_default_certificate(ingress_pods),
            "tool_warnings": tuple(dict.fromkeys(warnings)),
        }

    def routes_payload(self, snapshot: LiveDeploymentSnapshot) -> dict[str, Any]:
        node_ip, warnings = self._node_ip()
        snapshot_routes = _snapshot_routes(snapshot)
        hosts = sorted({route.host for route in snapshot_routes if route.host} or set(self._configured_hosts()))
        entries = [
            {
                "host": host,
                "target_ip": node_ip,
                "line": f"{node_ip} {host}" if node_ip else None,
                "source": "ingress" if any(route.host == host for route in snapshot_routes) else "configuration",
            }
            for host in hosts
        ]
        return {
            "findings": [],
            "hosts_entry_hints": {
                "target_ip": node_ip,
                "entries": entries,
                "managed_by_console": False,
                "note": "Add equivalent DNS or client hosts entries on machines that open the lab URLs.",
            },
            "routes": [
                {
                    "host": route.host,
                    "tls_secret": route.tls_secret,
                    "service_name": route.service_name,
                    "endpoints_ready": route.endpoints_ready,
                }
                for route in snapshot_routes
            ],
            "tool_warnings": tuple(dict.fromkeys(warnings)),
        }

    def _certificate_inventory(self, payload: object, referenced: list[str]) -> list[dict[str, Any]]:
        items = payload.get("items", []) if isinstance(payload, dict) else []
        by_name = {item.get("metadata", {}).get("name", ""): item for item in items}
        names = sorted(set(referenced) | {"tls"})
        inventory: list[dict[str, Any]] = []
        for name in names:
            item = by_name.get(name, {})
            data = item.get("data", {}) if isinstance(item, dict) else {}
            cert = data.get("tls.crt")
            metadata = _decode_certificate_metadata(cert) if cert else {}
            inventory.append(
                {
                    "name": name,
                    "namespace": self.namespace,
                    "present": bool(item),
                    "type": item.get("type") if isinstance(item, dict) else None,
                    "certificate_present": bool(cert),
                    "private_key_present": bool(data.get("tls.key")),
                    "common_name": metadata.get("common_name"),
                    "dns_names": metadata.get("dns_names", ()),
                    "not_before": metadata.get("not_before"),
                    "not_after": metadata.get("not_after"),
                    "referenced_by_ingress": name in referenced,
                }
            )
        return inventory

    def _traefik_default_certificate(self, payload: object) -> dict[str, Any]:
        expected = f"{self.namespace}/tls"
        args = []
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items:
            for container in (item.get("spec", {}) or {}).get("containers", []):
                args.extend(str(arg) for arg in container.get("args", []) or [])
        evidence = [arg for arg in args if "default-ssl-certificate" in arg or "defaultcertificate" in arg.lower()]
        configured = any(expected in arg for arg in evidence)
        if configured:
            status = "configured"
        elif evidence:
            status = "different"
        elif items:
            status = "not_detected"
        else:
            status = "unknown"
        return {"status": status, "expected_secret": expected, "evidence": evidence}

    def _node_ip(self) -> tuple[str | None, list[str]]:
        warnings: list[str] = []
        payload = self._json_command((*self.kubectl, "get", "nodes", "-o", "json"), warnings)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items:
            for address in ((item.get("status") or {}).get("addresses") or []):
                if address.get("type") == "InternalIP" and address.get("address"):
                    return str(address["address"]), warnings
        return None, warnings

    def _configured_hosts(self) -> tuple[str, ...]:
        if not self.env_file.is_file():
            return ()
        values = parse_env_text(self.env_file.read_text(encoding="utf-8")).values()
        hosts = [values[key] for key in LAB_HOST_KEYS if values.get(key)]
        domain = values.get("DOMAIN")
        if domain:
            hosts.append(f"dashboard.{domain}")
        return tuple(dict.fromkeys(hosts))

    def _json_command(self, command: tuple[str, ...], warnings: list[str]) -> object:
        runner = self.runner or _default_runner
        result = runner(command)
        if not result.ok:
            warnings.append(f"Command failed: {' '.join(command)}")
            return {}
        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            warnings.append(f"Command returned invalid JSON: {' '.join(command)}")
            return {}


def _default_runner(command: tuple[str, ...]) -> CommandResult:
    try:
        return run_command(command, timeout=20)
    except OSError as exc:
        return CommandResult(args=command, returncode=127, stdout="", stderr=str(exc), duration_seconds=0)


def _snapshot_routes(snapshot: LiveDeploymentSnapshot) -> tuple[RouteSummary, ...]:
    routes: list[RouteSummary] = []
    seen: set[tuple[str, str | None]] = set()
    for step in snapshot.steps:
        for route in step.routes:
            key = (route.host, route.service_name)
            if key not in seen:
                seen.add(key)
                routes.append(route)
    return tuple(routes)


def _decode_certificate_metadata(encoded: str) -> dict[str, Any]:
    try:
        pem = base64.b64decode(encoded).decode("utf-8", errors="replace")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".crt") as handle:
            handle.write(pem)
            handle.flush()
            decoded = ssl._ssl._test_decode_cert(handle.name)  # type: ignore[attr-defined]
    except Exception:
        return {}
    subject = decoded.get("subject", ())
    common_name = next((value for row in subject for key, value in row if key == "commonName"), None)
    dns_names = tuple(value for key, value in decoded.get("subjectAltName", ()) if key == "DNS")
    return {
        "common_name": common_name,
        "dns_names": dns_names,
        "not_before": decoded.get("notBefore"),
        "not_after": decoded.get("notAfter"),
    }
