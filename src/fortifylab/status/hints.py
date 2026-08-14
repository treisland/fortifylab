"""Progress hint analysis for live deployment status."""

from __future__ import annotations

from .model import EventSummary, HintSeverity, PodSummary, ProgressHint, RouteSummary


_BACKOFF_REASONS = {"ImagePullBackOff", "ErrImagePull", "CrashLoopBackOff"}
_PROBE_REASONS = {"Unhealthy"}
_PVC_REASONS = {"FailedScheduling"}


def hints_for_step(
    step_id: str,
    pods: tuple[PodSummary, ...],
    events: tuple[EventSummary, ...],
    routes: tuple[RouteSummary, ...] = (),
) -> tuple[ProgressHint, ...]:
    hints: list[ProgressHint] = []
    if any((pod.reason or "") in _BACKOFF_REASONS for pod in pods) or any(event.reason in _BACKOFF_REASONS for event in events):
        hints.append(
            ProgressHint(
                step_id,
                HintSeverity.BLOCKED,
                "image-or-container-backoff",
                "A pod is in image pull or container backoff.",
                "Open pod events and verify registry credentials, image name, and recent container logs.",
            )
        )
    if any(event.reason in _PROBE_REASONS for event in events):
        hints.append(
            ProgressHint(
                step_id,
                HintSeverity.WARNING,
                "probe-failure",
                "A startup or readiness probe is failing during startup.",
                "Check recent pod logs; early probe failures can be transient while the app warms up.",
            )
        )
    if any("unbound immediate PersistentVolumeClaims" in event.message for event in events) or any(event.reason in _PVC_REASONS and "PersistentVolumeClaims" in event.message for event in events):
        hints.append(
            ProgressHint(
                step_id,
                HintSeverity.BLOCKED,
                "pvc-unbound",
                "A pod is waiting for a PersistentVolumeClaim to bind.",
                "Inspect PVCs and the storage class for this namespace.",
            )
        )
    for route in routes:
        if not route.ingress_present:
            hints.append(
                ProgressHint(step_id, HintSeverity.BLOCKED, "ingress-missing", f"Ingress for {route.host} is missing.", "Inspect Helm values and ingress resources."),
            )
        elif not route.tls_secret:
            hints.append(
                ProgressHint(step_id, HintSeverity.WARNING, "tls-missing", f"Ingress for {route.host} has no TLS secret.", "Regenerate certificates and verify ingress TLS settings."),
            )
        elif not route.endpoints_ready:
            hints.append(
                ProgressHint(step_id, HintSeverity.WARNING, "endpoints-missing", f"Service endpoints for {route.host} are not ready.", "Inspect service selectors and pod readiness."),
            )
    return tuple(hints)
