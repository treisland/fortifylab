#!/bin/bash
# Idempotent Kubernetes scaling helpers for lab lifecycle operations.

fortify_kubectl() {
    if [ -n "${FORTIFY_OPERATION_KUBECTL:-}" ]; then
        $FORTIFY_OPERATION_KUBECTL "$@"
    else
        microk8s kubectl "$@"
    fi
}

fortify_scale_statefulset_if_exists() {
    local namespace="$1" statefulset="$2" replicas="$3"
    if fortify_kubectl -n "$namespace" get statefulset "$statefulset" >/dev/null 2>&1; then
        fortify_kubectl -n "$namespace" scale statefulset "$statefulset" --replicas="$replicas"
    else
        printf 'statefulset.apps "%s" not found in %s namespace; already stopped.
' "$statefulset" "$namespace"
    fi
}
