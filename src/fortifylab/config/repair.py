"""Validation and repair helpers for derived Fortify Lab host/URL values."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .envfile import EnvDocument, EnvUpdate


HOST_KEYS = ("SSC", "LIM", "SCDAST", "SCSAST", "LAB_HOST")
URL_KEYS = ("SSC_URL", "LIM_URL", "LIM_API_URL", "SCDAST_URL", "SCSAST_URL", "SCSAST_CTRL_URL", "LAB_URL")
PLACEHOLDER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
DOMAIN_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)+$")


def validate_domain(value: str | None) -> bool:
    return bool(value and DOMAIN_RE.match(value))


def expected_host(key: str, domain: str) -> str | None:
    mapping = {
        "SSC": f"ssc.{domain}",
        "LIM": f"lim.{domain}",
        "SCDAST": f"dast.{domain}",
        "SCSAST": f"sast.{domain}",
        "LAB_HOST": f"lab.{domain}",
    }
    return mapping.get(key)


def expected_url(key: str, domain: str) -> str | None:
    mapping = {
        "SSC_URL": f"https://ssc.{domain}",
        "LIM_URL": f"https://lim.{domain}",
        "LIM_API_URL": f"https://lim.{domain}/LIM.API",
        "SCDAST_URL": f"https://dast.{domain}",
        "SCSAST_URL": f"https://sast.{domain}",
        "SCSAST_CTRL_URL": f"https://sast.{domain}/scancentral-ctrl/",
        "LAB_URL": f"https://lab.{domain}:8443",
    }
    return mapping.get(key)


def domain_url_updates(domain: str) -> tuple[EnvUpdate, ...]:
    normalized = domain.lower()
    return (
        EnvUpdate("DOMAIN", normalized),
        EnvUpdate("SSC", "ssc.$DOMAIN", expression=True),
        EnvUpdate("LIM", "lim.$DOMAIN", expression=True),
        EnvUpdate("SCDAST", "dast.$DOMAIN", expression=True),
        EnvUpdate("SCSAST", "sast.$DOMAIN", expression=True),
        EnvUpdate("LAB_HOST", "lab.$DOMAIN", expression=True),
        EnvUpdate("SSC_URL", "https://$SSC", expression=True),
        EnvUpdate("LIM_URL", "https://$LIM", expression=True),
        EnvUpdate("LIM_API_URL", "https://$LIM/LIM.API", expression=True),
        EnvUpdate("SCDAST_URL", "https://$SCDAST", expression=True),
        EnvUpdate("SCSAST_URL", "https://$SCSAST", expression=True),
        EnvUpdate("SCSAST_CTRL_URL", "https://$SCSAST/scancentral-ctrl/", expression=True),
        EnvUpdate("LAB_URL", "https://$LAB_HOST:8443", expression=True),
    )


def validate_hosts_and_urls(document: EnvDocument) -> tuple[str, ...]:
    values = document.values()
    domain = values.get("DOMAIN")
    issues: list[str] = []
    if not validate_domain(domain):
        issues.append("DOMAIN must be a lowercase DNS-style domain such as fortifydemo.com.")
        domain = domain or "fortifydemo.com"
    assert domain is not None

    for key in HOST_KEYS:
        value = values.get(key)
        expected = expected_host(key, domain)
        if not value:
            issues.append(f"{key} is unset; expected {expected}.")
        elif _placeholder_like(value):
            issues.append(f"{key} is set to placeholder-like value {value}; expected {expected}.")
        elif not validate_domain(value):
            issues.append(f"{key} must be a lowercase DNS hostname with at least one dot; current value is {value}; expected {expected}.")
        elif expected and value != expected:
            issues.append(f"{key} is {value}; expected derived value {expected} for DOMAIN={domain}.")

    for key in URL_KEYS:
        value = values.get(key)
        expected = expected_url(key, domain)
        if not value:
            issues.append(f"{key} is unset; expected {expected}.")
            continue
        if _placeholder_like(value):
            issues.append(f"{key} is set to placeholder-like value {value}; expected {expected}.")
            continue
        url_host = _url_host(value)
        if not url_host:
            issues.append(f"{key} must be an https URL; current value is {value}; expected {expected}.")
        elif expected and value != expected:
            issues.append(f"{key} is {value}; expected derived value {expected} for DOMAIN={domain}.")
    return tuple(issues)


def _placeholder_like(value: str) -> bool:
    return bool(PLACEHOLDER_RE.match(value))


def _url_host(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return parsed.hostname
