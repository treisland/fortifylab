"""Recovery suggestion heuristics for the Fortify Lab cockpit API."""

from __future__ import annotations

from typing import Any


def recovery_suggestions_payload(
    *,
    snapshot_payload: dict[str, Any],
    config_payload: dict[str, Any],
    services_payload: dict[str, Any],
    routes_payload: dict[str, Any],
    certificates_payload: dict[str, Any],
    diagnostics_payload: dict[str, Any],
) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []
    suggestions.extend(_invalid_env(config_payload))
    suggestions.extend(_missing_secrets(certificates_payload, snapshot_payload))
    suggestions.extend(_traefik_default_cert(certificates_payload))
    suggestions.extend(_service_health(services_payload))
    suggestions.extend(_image_pull(snapshot_payload, diagnostics_payload))
    suggestions.extend(_route_mismatch(services_payload, routes_payload))
    result = _dedupe(suggestions)
    return {"suggestions": result, "count": len(result)}


def _invalid_env(config: dict[str, Any]) -> list[dict[str, Any]]:
    issues = list(config.get("issues") or [])
    if not issues:
        return []
    return [_suggestion(
        "invalid-env-placeholders",
        "Configuration values need repair",
        "FortifyLab found missing, invalid, or placeholder-like .env values before applying Kubernetes changes.",
        "blocked",
        "Open Configuration and run Repair derived host and URL values from DOMAIN, then retry pre-flight.",
        "configuration/env",
        evidence=issues[:5],
    )]


def _missing_secrets(certificates: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = certificates.get("inventory") or []
    missing_tls = [
        item.get("name")
        for item in inventory
        if item.get("referenced_by_ingress") and (not item.get("present") or not item.get("certificate_present") or not item.get("private_key_present"))
    ]
    secret_steps = [
        step for step in snapshot.get("steps", [])
        if step.get("step_id") == "secrets" and step.get("state") in {"pending", "blocked", "failed"}
    ]
    if not missing_tls and not secret_steps:
        return []
    evidence = [f"TLS secret {name} is incomplete or missing." for name in missing_tls]
    evidence.extend(step.get("detail") for step in secret_steps if step.get("detail"))
    return [_suggestion(
        "missing-kubernetes-secrets",
        "Required Kubernetes secrets are missing",
        "One or more required Kubernetes secrets or TLS key pairs are not ready.",
        "blocked",
        "Run Create Kubernetes Secrets or Generate TLS certificates, then verify the secrets step again.",
        "guided/secrets",
        evidence=evidence[:5],
    )]


def _traefik_default_cert(certificates: dict[str, Any]) -> list[dict[str, Any]]:
    traefik = certificates.get("traefik_default_certificate") or {}
    status = traefik.get("status")
    if status in {"configured", "unknown"}:
        return []
    return [_suggestion(
        "traefik-default-cert",
        "Traefik may be serving its default certificate",
        "Ingress TLS is not clearly configured to use the FortifyLab TLS secret.",
        "warning" if status == "not_detected" else "blocked",
        "Regenerate/apply TLS, ensure Traefik references fortify/tls as the default certificate, and restart ingress if needed.",
        "networking/tls",
        evidence=traefik.get("evidence") or [f"status={status}"],
    )]


def _service_health(services: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for service in services.get("services", []):
        checks = service.get("checks") or {}
        host = service.get("host") or service.get("url") or service.get("label")
        dns = checks.get("dns") or {}
        http = checks.get("http") or {}
        tls = checks.get("tls") or {}
        if dns.get("state") == "blocked":
            suggestions.append(_suggestion(
                f"dns-miss-{service.get('service_id')}",
                f"DNS does not resolve {host}",
                "The service hostname is not resolving from the console environment.",
                "blocked",
                "Add DNS or hosts-file entries pointing the lab names at the ingress node, then refresh service health.",
                "networking/dns",
                service_id=service.get("service_id"),
                evidence=[dns.get("message")],
            ))
        tls_text = " ".join(str(value) for value in tls.values()).lower()
        if "traefik default" in tls_text:
            suggestions.append(_suggestion(
                f"traefik-default-cert-{service.get('service_id')}",
                f"{host} is serving the Traefik default certificate",
                "The route matched TLS but the certificate identity is not the FortifyLab certificate.",
                "blocked",
                "Verify the ingress TLS secret and Traefik default certificate configuration, then reload ingress.",
                "networking/tls",
                service_id=service.get("service_id"),
                evidence=[tls.get("message")],
            ))
        if http.get("status_code") == 404:
            suggestions.append(_suggestion(
                f"route-404-{service.get('service_id')}",
                f"{host} returns 404",
                "The request reached ingress, but no route appears to match the requested hostname/path.",
                "blocked",
                "Inspect ingress host rules, client hostname, and service route names for this service.",
                "networking/dns",
                service_id=service.get("service_id"),
                evidence=[http.get("message")],
            ))
        if http.get("status_code", 0) >= 500 or http.get("state") == "warning":
            suggestions.append(_suggestion(
                f"backend-unreachable-{service.get('service_id')}",
                f"{host} backend is not healthy",
                "The service route is reachable but the backend returned an error or could not complete the probe.",
                "warning",
                "Open the service logs and diagnostics to inspect startup errors, readiness probes, and backend dependencies.",
                "logs/workspace",
                service_id=service.get("service_id"),
                evidence=[http.get("message")],
            ))
    return suggestions


def _image_pull(snapshot: dict[str, Any], diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[str] = []
    for step in snapshot.get("steps", []):
        for pod in step.get("pods", []):
            reason = str(pod.get("reason") or "")
            if reason in {"ImagePullBackOff", "ErrImagePull"}:
                evidence.append(f"{pod.get('name')} is {reason}.")
        for event in step.get("events", []):
            if "pull" in str(event.get("reason", "")).lower() or "pull" in str(event.get("message", "")).lower():
                evidence.append(str(event.get("message") or event.get("reason")))
    for finding in diagnostics.get("findings", []):
        if "image" in str(finding.get("message", "")).lower() or "registry" in str(finding.get("next_inspection", "")).lower():
            evidence.append(str(finding.get("message") or finding.get("next_inspection")))
    if not evidence:
        return []
    return [_suggestion(
        "image-pull-backoff",
        "Container image pull is blocked",
        "Kubernetes cannot pull at least one required FortifyLab image.",
        "blocked",
        "Refresh Docker registry credentials into Kubernetes image pull secrets, then retry the affected deployment.",
        "operations/support-bundle",
        evidence=evidence[:5],
    )]


def _route_mismatch(services: dict[str, Any], routes: dict[str, Any]) -> list[dict[str, Any]]:
    live_hosts = {route.get("host") for route in routes.get("routes", []) if route.get("host")}
    suggestions: list[dict[str, Any]] = []
    for service in services.get("services", []):
        checks = service.get("checks") or {}
        ingress = checks.get("ingress") or {}
        host = service.get("host")
        if host and live_hosts and host not in live_hosts:
            suggestions.append(_suggestion(
                f"route-host-mismatch-{service.get('service_id')}",
                f"No live ingress route for {host}",
                "The configured service URL does not match any live ingress host reported by Kubernetes.",
                "blocked",
                "Repair .env host values or recreate the ingress so the configured URL and Kubernetes host rule match.",
                "configuration/env",
                service_id=service.get("service_id"),
                evidence=[f"live_hosts={', '.join(sorted(live_hosts))}"],
            ))
        elif ingress.get("state") == "blocked":
            suggestions.append(_suggestion(
                f"missing-ingress-{service.get('service_id')}",
                f"Ingress is missing for {host}",
                "The service has no matching live ingress route.",
                "blocked",
                "Start or upgrade the service, then inspect ingress and endpoint readiness.",
                "networking/dns",
                service_id=service.get("service_id"),
                evidence=[ingress.get("message")],
            ))
    return suggestions


def _suggestion(
    suggestion_id: str,
    title: str,
    summary: str,
    severity: str,
    next_action: str,
    help_topic: str,
    *,
    service_id: str | None = None,
    evidence: list[Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": suggestion_id,
        "title": title,
        "summary": summary,
        "severity": severity,
        "next_action": next_action,
        "help_topic": help_topic,
        "evidence": [str(item) for item in (evidence or []) if item],
    }
    if service_id:
        payload["service_id"] = service_id
    return payload


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("id"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
