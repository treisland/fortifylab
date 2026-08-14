#!/bin/bash
# Shared lifecycle helpers for intentionally vulnerable OWASP sample apps.

set -eo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

# shellcheck source=../../scripts/lib/k8s-hostnames.sh
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-hostnames.sh"
# shellcheck source=../../scripts/lib/coredns-lab-hosts.sh
source "$FORTIFY_HOME_K8S/scripts/lib/coredns-lab-hosts.sh"

sample_kubectl() {
    if [ -n "${FORTIFY_OPERATION_KUBECTL:-}" ]; then
        # shellcheck disable=SC2086
        $FORTIFY_OPERATION_KUBECTL "$@"
    else
        microk8s kubectl "$@"
    fi
}

sample_app_load_env() {
    # shellcheck disable=SC1090
    source "$FORTIFY_HOME_K8S/.env"
    sample_app_apply_defaults
}

sample_app_apply_defaults() {
    local domain="${DOMAIN:-fortifydemo.com}"
    export JUICE_SHOP="${JUICE_SHOP:-juice-shop.$domain}"
    export WEBGOAT="${WEBGOAT:-webgoat.$domain}"
    export DVWA="${DVWA:-dvwa.$domain}"
    export JUICE_SHOP_URL="${JUICE_SHOP_URL:-https://$JUICE_SHOP}"
    export WEBGOAT_URL="${WEBGOAT_URL:-https://$WEBGOAT}"
    export DVWA_URL="${DVWA_URL:-https://$DVWA}"
}

sample_app_start() {
    local manifest="$1" host_var="$2" host_value="$3"
    sample_app_load_env
    fortify_require_k8s_hostname "$host_var" "$host_value"
    fortify_ensure_coredns_lab_hosts
    envsubst < "$manifest" | sample_kubectl -n "$NAMESPACE" apply -f -
}

sample_app_stop_deployment() {
    local deployment="$1"
    sample_app_load_env
    if sample_kubectl -n "$NAMESPACE" get deployment "$deployment" >/dev/null 2>&1; then
        sample_kubectl -n "$NAMESPACE" scale deployment "$deployment" --replicas=0
    else
        printf 'deployment.apps "%s" not found in %s namespace; already stopped.\n' "$deployment" "$NAMESPACE"
    fi
}

sample_app_destroy() {
    local manifest="$1"
    sample_app_load_env
    envsubst < "$manifest" | sample_kubectl -n "$NAMESPACE" delete -f - --ignore-not-found
}
