"""Contextual help topics for the Fortify Lab web console."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HelpTopic:
    topic_id: str
    title: str
    summary: str
    docs: tuple[str, ...]
    applies_to: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.topic_id,
            "title": self.title,
            "summary": self.summary,
            "docs": list(self.docs),
            "applies_to": list(self.applies_to),
            "actions": list(self.actions),
        }

    def to_detail(self) -> dict[str, Any]:
        return self.to_summary() | {
            "content": self.summary,
            "content_policy": "concise-summary",
            "redaction": "Help topics reference existing docs and do not embed secrets, private keys, licenses, or full runbooks.",
        }


TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic(
        "onboarding/overview",
        "Operator cockpit overview",
        "Start here when using the web console as the primary path through configuration, deployment, monitoring, and launch.",
        ("docs/getting-started/index.md", "docs/lab-use.md", "docs/operations/web-console-manual-tests.md"),
        ("guided", "first-run", "web-console", "onboarding/overview"),
    ),
    HelpTopic(
        "configuration/env",
        "Configuration and .env repair",
        "Review domain, host, URL, version, and credential settings before the console applies Kubernetes changes.",
        ("docs/configuration/index.md", "docs/operations/troubleshooting.md", "scripts/wizard/env.sh"),
        ("configuration", "preflight", "invalid-env", "configuration/env"),
        ("repair-config",),
    ),
    HelpTopic(
        "networking/dns",
        "DNS and client hosts entries",
        "Use this when service URLs do not resolve or client machines need hosts-file entries for the lab domain.",
        ("docs/operations/networking-and-tls.md", "docs/help/urls.txt"),
        ("dns", "routes", "service-launchpad", "networking/dns"),
    ),
    HelpTopic(
        "networking/tls",
        "TLS certificates and root CA trust",
        "Generate or import lab TLS material, export the mkcert root CA, and verify browsers trust the served certificate.",
        ("docs/operations/networking-and-tls.md", "docs/help/urls.txt", "scripts/lib/tls.sh"),
        ("tls", "certificates", "traefik", "networking/tls"),
        ("generate-certs", "export-root-ca"),
    ),
    HelpTopic(
        "guided/deployment",
        "Guided deployment",
        "Follow the ordered deployment journey and inspect live state, diagnostics, and logs while steps run.",
        ("docs/getting-started/index.md", "docs/operations/deployment-and-lifecycle.md", "scripts/wizard/guided.sh"),
        ("guided", "timeline", "deployment", "guided/deployment"),
    ),
    HelpTopic(
        "guided/secrets",
        "Kubernetes secrets",
        "Create and verify required Kubernetes secrets without exposing secret values in logs, APIs, or diagnostics.",
        ("docs/operations/secrets-and-licenses.md", "docs/help/overview.txt", "scripts/create-secrets.sh"),
        ("secrets", "licenses", "preflight", "guided/secrets"),
        ("create-secrets",),
    ),
    HelpTopic(
        "services/ssc",
        "Software Security Center",
        "Deploy, monitor, open, and troubleshoot SSC readiness, ingress, startup, and backend health.",
        ("docs/fortify/ssc.md", "docs/operations/troubleshooting.md"),
        ("ssc", "service-launchpad", "backend-500", "services/ssc"),
        ("start-ssc", "stop-ssc", "view-ssc-logs"),
    ),
    HelpTopic(
        "services/databases",
        "MySQL and PostgreSQL",
        "Inspect database readiness, persistent volume state, startup probes, and authenticated query checks.",
        ("docs/fortify/mysql.md", "docs/fortify/postgresql.md", "docs/operations/deployment-and-lifecycle.md"),
        ("mysql", "postgresql", "storage", "services/databases"),
    ),
    HelpTopic(
        "logs/workspace",
        "Log workspace",
        "Open recent or following logs with pod context, timestamps, filtering, copy, and download support.",
        ("docs/operations/diagnostics.md", "docs/operations/troubleshooting.md"),
        ("logs", "diagnostics", "evidence", "logs/workspace"),
    ),
    HelpTopic(
        "operations/lifecycle",
        "Lifecycle controls",
        "Start, stop, shut down, bring up, or destroy lab resources with guarded confirmations and audit evidence.",
        ("docs/operations/deployment-and-lifecycle.md", "docs/operations/backup-and-recovery.md"),
        ("lifecycle", "actions", "audit", "operations/lifecycle"),
    ),
    HelpTopic(
        "operations/support-bundle",
        "Diagnostics and support bundle",
        "Collect redacted evidence about cluster health, routes, events, configuration, and selected logs for support.",
        ("docs/operations/diagnostics.md", "docs/operations/runbooks.md"),
        ("diagnostics", "support", "evidence", "operations/support-bundle"),
    ),
    HelpTopic(
        "operations/first-scan",
        "First scan handoff",
        "After deployment, use the first-scan runbook to prove SSC, LIM, and ScanCentral are usable.",
        ("docs/operations/first-scan.md", "docs/examples/first-scan/README.md"),
        ("first-scan", "post-deployment", "runbook", "operations/first-scan"),
    ),
)


def help_topics_payload() -> dict[str, Any]:
    topics = sorted(TOPICS, key=lambda topic: topic.topic_id)
    return {
        "topics": [topic.to_summary() for topic in topics],
        "count": len(topics),
        "content_policy": "concise summaries with references to existing docs/help/runbooks",
    }


def help_topic_payload(topic_id: str) -> dict[str, Any] | None:
    topic = _topic_by_id().get(topic_id)
    if topic is None:
        return None
    return topic.to_detail()


def topics_for_context(*contexts: str) -> list[dict[str, Any]]:
    wanted = {context for context in contexts if context}
    matches = [topic.to_summary() for topic in TOPICS if wanted.intersection(topic.applies_to)]
    return sorted(matches, key=lambda topic: topic["id"])


def _topic_by_id() -> dict[str, HelpTopic]:
    return {topic.topic_id: topic for topic in TOPICS}
