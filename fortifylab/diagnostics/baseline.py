"""Default read-only diagnostic check catalog."""

from __future__ import annotations

from .models import DiagnosticCheck, DiagnosticSeverity


def default_checks() -> tuple[DiagnosticCheck, ...]:
    return (
        DiagnosticCheck("prereq.repo", "repository files are present", "prerequisites"),
        DiagnosticCheck("license.file", "license configuration can be inspected", "license"),
        DiagnosticCheck("cluster.kubectl.client", "kubectl client is available", "cluster", DiagnosticSeverity.WARN, ("kubectl", "version", "--client")),
        DiagnosticCheck("pods.summary", "pod status can be inspected", "pods", DiagnosticSeverity.WARN, ("kubectl", "get", "pods")),
        DiagnosticCheck("registry.auth", "registry auth can be inspected", "registry", DiagnosticSeverity.WARN, ("kubectl", "get", "secret", "regcred", "-o", "json")),
        DiagnosticCheck("tls.identity", "TLS identity can be inspected", "tls", DiagnosticSeverity.WARN, ("kubectl", "get", "secret", "fortify-tls", "-o", "json")),
    )
