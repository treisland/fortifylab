"""Authoritative cockpit snapshot composition for the web console."""

from __future__ import annotations

from typing import Any

from fortifylab.status import LiveDeploymentSnapshot
from fortifylab.web.help import help_topic_payload
from fortifylab.web.recovery import recovery_suggestions_payload


def cockpit_state_payload(
    *,
    snapshot: LiveDeploymentSnapshot,
    deployment_status: dict[str, Any],
    guide: dict[str, Any],
    journey: dict[str, Any],
    services: dict[str, Any],
    service_health: dict[str, Any],
    routes: dict[str, Any],
    certificates: dict[str, Any],
    security: dict[str, Any],
    lifecycle: dict[str, Any],
    jobs: dict[str, Any],
    audit: dict[str, Any],
    diagnostics: dict[str, Any],
    logs: dict[str, Any],
    config: dict[str, Any],
    support_bundle: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recovery = recovery_suggestions_payload(
        snapshot_payload=deployment_status,
        config_payload=config,
        services_payload=service_health,
        routes_payload=routes,
        certificates_payload=certificates,
        diagnostics_payload=diagnostics,
    )
    return {
        "version": 1,
        "generated_at": snapshot.generated_at,
        "namespace": snapshot.namespace,
        "profile": snapshot.profile,
        "overall_state": snapshot.overall_state.value,
        "state_sources": {
            "cluster": "live",
            "services": "live",
            "routes": "live",
            "certificates": "live",
            "lifecycle_jobs": "runtime",
            "action_audit": "runtime",
            "wizard_progress": "live-first",
            "wizard_history": "historical",
        },
        "wizard_state": {
            "live_first": True,
            "current": {"overall_state": guide.get("overall_state"), "steps": guide.get("steps", [])},
            "historical": {
                "available": False,
                "note": "Historical wizard completion is intentionally separate from live Kubernetes state.",
            },
        },
        "guide": guide,
        "journey": journey,
        "pipeline": pipeline or {},
        "deployment": deployment_status,
        "configuration": config,
        "services": services,
        "health": service_health,
        "routes": routes,
        "certificates": certificates,
        "security": security,
        "lifecycle": lifecycle,
        "jobs": jobs,
        "audit": audit,
        "diagnostics": diagnostics,
        "logs": logs,
        "support_bundle": support_bundle or {},
        "recovery": recovery,
        "help": {"suggested_topics": _suggested_topics(recovery), "topics_endpoint": "/api/help/topics"},
        "redaction": "Secrets, credentials, private keys, licenses, and raw mutating commands are not returned.",
    }


def _suggested_topics(recovery: dict[str, Any]) -> list[dict[str, Any]]:
    topics = []
    seen = set()
    for suggestion in recovery.get("suggestions", []):
        topic_id = suggestion.get("help_topic")
        if not topic_id or topic_id in seen:
            continue
        topic = help_topic_payload(str(topic_id))
        if topic:
            topics.append({key: topic[key] for key in ("id", "title", "summary", "docs", "applies_to", "actions")})
            seen.add(topic_id)
    return topics
