#!/bin/bash
# Idempotent Kubernetes teardown helpers for lab destroy scripts.

fortify_helm_delete_if_exists() {
    local namespace="$1" release="$2"
    if microk8s helm -n "$namespace" status "$release" >/dev/null 2>&1; then
        microk8s helm -n "$namespace" delete "$release"
    else
        printf 'release "%s" already absent; skipping Helm delete.\n' "$release"
    fi
}

fortify_kubectl_delete_file_ignore_not_found() {
    local namespace="$1" manifest="$2"
    microk8s kubectl -n "$namespace" delete -f "$manifest" --ignore-not-found
}
