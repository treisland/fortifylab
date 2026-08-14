"""Service registry and bounded URL health checks for Fortify Lab."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import http.client
from pathlib import Path
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

from fortifylab.config import EnvDocument, expected_host, expected_url, parse_env_text, validate_hosts_and_urls

from .model import LiveDeploymentSnapshot, RouteSummary


DEFAULT_DOMAIN = "fortifydemo.com"
SERVICE_SPECS = (
    ("ssc", "Software Security Center", "SSC", "SSC_URL", "web"),
    ("lim", "License and Infrastructure Manager", "LIM", "LIM_URL", "web"),
    ("lim_api", "LIM API", "LIM", "LIM_API_URL", "api"),
    ("sast", "ScanCentral SAST Controller", "SCSAST", "SCSAST_CTRL_URL", "api"),
    ("dast", "ScanCentral DAST", "SCDAST", "SCDAST_URL", "web"),
    ("dashboard", "Kubernetes Dashboard", None, None, "web"),
)


@dataclass(frozen=True)
class ServiceRecord:
    service_id: str
    label: str
    kind: str
    host_key: str | None
    url_key: str | None
    host: str
    url: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegistryPayload:
    source: str
    domain: str
    services: tuple[ServiceRecord, ...]
    config_issues: tuple[str, ...] = ()
    secrets_redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "domain": self.domain,
            "services": [service.to_dict() for service in self.services],
            "config_issues": list(self.config_issues),
            "secrets_redacted": self.secrets_redacted,
        }


class URLHealthChecker:
    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        self.timeout_seconds = timeout_seconds

    def check(self, service: ServiceRecord) -> dict[str, Any]:
        parsed = urlparse(service.url)
        host = parsed.hostname or service.host
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        dns = self._dns(host, port)
        http = self._http(parsed, host, port)
        tls = self._tls_from_http(parsed, http)
        return _health_payload(service, dns=dns, tls=tls, http=http, ingress=None)

    def _dns(self, host: str, port: int) -> dict[str, Any]:
        try:
            results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            return _check("blocked", f"DNS did not resolve {host}.", error=_safe_error(exc))
        except OSError as exc:
            return _check("warning", f"DNS lookup for {host} could not complete.", error=_safe_error(exc))
        addresses = sorted({item[4][0] for item in results if item[4]})
        if not addresses:
            return _check("blocked", f"DNS did not return an address for {host}.")
        return _check("ok", f"DNS resolves {host}.", address_count=len(addresses))

    def _http(self, parsed: Any, host: str, port: int) -> dict[str, Any]:
        if parsed.scheme not in {"http", "https"}:
            return _check("blocked", "URL must use http or https.", scheme=parsed.scheme)
        connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        connection = None
        try:
            connection = connection_cls(host, port=port, timeout=self.timeout_seconds)
            connection.request("HEAD", path)
            response = connection.getresponse()
            response.read()
        except ssl.SSLError as exc:
            return _check("blocked", "TLS handshake failed.", error=_safe_error(exc), tls_error=True)
        except TimeoutError as exc:
            return _check("warning", "HTTP probe timed out.", error=_safe_error(exc))
        except OSError as exc:
            return _check("warning", "HTTP probe could not connect.", error=_safe_error(exc))
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        state = "ok" if response.status < 500 else "warning"
        return _check(state, f"HTTP returned {response.status}.", status_code=response.status)

    @staticmethod
    def _tls_from_http(parsed: Any, http: dict[str, Any]) -> dict[str, Any]:
        if parsed.scheme != "https":
            return _check("unknown", "TLS is not applicable for non-HTTPS URLs.")
        if http.get("tls_error"):
            return _check("blocked", "TLS handshake failed.", error=http.get("error"))
        if http["state"] == "ok":
            return _check("ok", "TLS handshake completed.")
        return _check("unknown", "TLS was not confirmed because the HTTPS probe did not complete.")


def build_service_registry(env_file: Path | None = None, *, env_text: str | None = None) -> RegistryPayload:
    document, source = _load_document(env_file, env_text=env_text)
    values = document.values()
    domain = values.get("DOMAIN") or DEFAULT_DOMAIN
    services: list[ServiceRecord] = []
    for service_id, label, host_key, url_key, kind in SERVICE_SPECS:
        host = _service_host(service_id, host_key, values, domain)
        url = _service_url(service_id, url_key, values, domain)
        source_label = "env" if (host_key and values.get(host_key)) or (url_key and values.get(url_key)) else "default"
        services.append(ServiceRecord(service_id, label, kind, host_key, url_key, host, url, source_label))
    return RegistryPayload(source=source, domain=domain, services=tuple(services), config_issues=validate_hosts_and_urls(document))


def service_health_payload(
    registry: RegistryPayload,
    *,
    checker: URLHealthChecker | Any | None = None,
    snapshot: LiveDeploymentSnapshot | None = None,
) -> dict[str, Any]:
    checker = checker or URLHealthChecker()
    routes_by_host = _routes_by_host(snapshot)
    results = []
    for service in registry.services:
        result = checker.check(service)
        ingress = _ingress_check(service, routes_by_host.get(service.host))
        result["checks"]["ingress"] = ingress
        result["hints"] = _hints_for_checks(result["checks"])
        results.append(result)
    return {"source": registry.source, "services": results, "secrets_redacted": True}


def _load_document(env_file: Path | None, *, env_text: str | None) -> tuple[EnvDocument, str]:
    if env_text is not None:
        return parse_env_text(env_text), "provided"
    candidates = []
    if env_file is not None:
        candidates.append(Path(env_file))
    else:
        candidates.extend((Path.cwd() / ".env", Path.cwd() / ".env.example"))
    for candidate in candidates:
        if candidate.is_file():
            return parse_env_text(candidate.read_text(encoding="utf-8")), str(candidate)
    return parse_env_text(_default_env_text()), "defaults"


def _default_env_text() -> str:
    rows = [f"DOMAIN={DEFAULT_DOMAIN}"]
    for key in ("SSC", "LIM", "SCDAST", "SCSAST"):
        rows.append(f"{key}={expected_host(key, DEFAULT_DOMAIN)}")
    for key in ("SSC_URL", "LIM_URL", "LIM_API_URL", "SCDAST_URL", "SCSAST_URL", "SCSAST_CTRL_URL"):
        rows.append(f"{key}={expected_url(key, DEFAULT_DOMAIN)}")
    return "\n".join(rows) + "\n"

def _service_host(service_id: str, host_key: str | None, values: dict[str, str], domain: str) -> str:
    if service_id == "dashboard":
        return f"dashboard.{domain}"
    if host_key and values.get(host_key):
        return values[host_key]
    if host_key:
        expected = expected_host(host_key, domain)
        if expected:
            return expected
    return f"{service_id}.{domain}"


def _service_url(service_id: str, url_key: str | None, values: dict[str, str], domain: str) -> str:
    if service_id == "dashboard":
        return f"https://dashboard.{domain}"
    if url_key and values.get(url_key):
        return values[url_key]
    if url_key:
        expected = expected_url(url_key, domain)
        if expected:
            return expected
    return f"https://{service_id}.{domain}"


def _routes_by_host(snapshot: LiveDeploymentSnapshot | None) -> dict[str, RouteSummary]:
    if snapshot is None:
        return {}
    routes: dict[str, RouteSummary] = {}
    for step in snapshot.steps:
        for route in step.routes:
            routes[route.host] = route
    return routes


def _ingress_check(service: ServiceRecord, route: RouteSummary | None) -> dict[str, Any]:
    if route is None:
        return _check("unknown", f"No live ingress data is available for {service.host}.")
    if not route.ingress_present:
        return _check("blocked", f"Ingress for {service.host} is missing.")
    if not route.tls_secret:
        return _check("warning", f"Ingress for {service.host} has no TLS secret.", service_name=route.service_name)
    if not route.endpoints_ready:
        return _check("warning", f"Service endpoints for {service.host} are not ready.", service_name=route.service_name, tls_secret_present=True)
    return _check("ok", f"Ingress for {service.host} has TLS and ready endpoints.", service_name=route.service_name, tls_secret_present=True)


def _health_payload(
    service: ServiceRecord,
    *,
    dns: dict[str, Any],
    tls: dict[str, Any],
    http: dict[str, Any],
    ingress: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = {"dns": dns, "tls": tls, "http": http}
    if ingress is not None:
        checks["ingress"] = ingress
    return {
        "service_id": service.service_id,
        "label": service.label,
        "url": service.url,
        "host": service.host,
        "checks": checks,
        "hints": _hints_for_checks(checks),
    }


def _hints_for_checks(checks: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    for name, check in checks.items():
        state = check.get("state")
        if state not in {"blocked", "warning"}:
            continue
        hints.append(
            {
                "check": name,
                "severity": state,
                "message": str(check.get("message", "Check needs attention.")),
                "next_inspection": _next_inspection(name, state),
            }
        )
    return hints


def _next_inspection(name: str, state: str) -> str:
    if name == "dns":
        return "Verify client DNS or hosts entries point the lab domain at the ingress node."
    if name == "tls":
        return "Verify the root CA is trusted and the ingress certificate covers this hostname."
    if name == "ingress":
        return "Inspect ingress, TLS secret, service selector, and endpoint readiness in the Fortify namespace."
    if state == "blocked":
        return "Open the service URL from the same client and inspect the connection error."
    return "Check whether the service is still starting or returning a transient upstream response."


def _check(state: str, message: str, **details: Any) -> dict[str, Any]:
    payload = {"state": state, "message": message}
    payload.update({key: value for key, value in details.items() if value not in (None, "")})
    return payload


def _safe_error(exc: BaseException) -> str:
    return exc.__class__.__name__
