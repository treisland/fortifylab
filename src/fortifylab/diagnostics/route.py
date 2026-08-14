"""Ingress, DNS, and TLS route diagnostic helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteCheck:
    host: str
    expected_ip: str
    resolved_ip: str | None
    ingress_present: bool
    tls_secret_present: bool
    http_status: int | None = None
    tls_common_name: str | None = None


def route_findings(checks: tuple[RouteCheck, ...]) -> tuple[str, ...]:
    findings: list[str] = []
    for check in checks:
        if not check.resolved_ip:
            findings.append(f"{check.host}: DNS does not resolve on this machine.")
        elif check.resolved_ip != check.expected_ip:
            findings.append(f"{check.host}: DNS resolves to {check.resolved_ip}, expected {check.expected_ip}.")
        if not check.ingress_present:
            findings.append(f"{check.host}: matching ingress host is missing.")
        if not check.tls_secret_present:
            findings.append(f"{check.host}: TLS secret is missing; Traefik may serve its default certificate.")
        if check.tls_common_name and check.tls_common_name.upper() == "TRAEFIK DEFAULT CERT":
            findings.append(f"{check.host}: served certificate is the Traefik default certificate.")
        if check.http_status == 404:
            findings.append(f"{check.host}: route returned 404; ingress host or router matching may be wrong.")
    return tuple(findings)
