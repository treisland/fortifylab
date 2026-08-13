#!/bin/bash

set -euo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

# shellcheck disable=SC1091
source "$FORTIFY_HOME_K8S/.env"
# shellcheck source=../../scripts/lib/traefik-backend.sh
source "$FORTIFY_HOME_K8S/scripts/lib/traefik-backend.sh"

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECTL_CMD="${KUBECTL_CMD:-microk8s kubectl}"
read -r -a KUBECTL_ARGS <<< "$KUBECTL_CMD"
DASHBOARD_HOST="dashboard.${DOMAIN}"

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || [[ "$DOMAIN" == *..* ]]; then
    printf 'Invalid DOMAIN for Dashboard ingress: %s\n' "$DOMAIN" >&2
    exit 1
fi

for certificate_file in "$SERVER_CERT" "$SERVER_KEY"; do
    if [ ! -s "$certificate_file" ]; then
        printf 'Dashboard TLS input is missing or empty: %s\n' "$certificate_file" >&2
        exit 1
    fi
done

microk8s enable dashboard >/dev/null

if "${KUBECTL_ARGS[@]}" -n kubernetes-dashboard get service kubernetes-dashboard-kong-proxy >/dev/null 2>&1; then
    DASHBOARD_NAMESPACE=kubernetes-dashboard
    DASHBOARD_SERVICE=kubernetes-dashboard-kong-proxy
    "${KUBECTL_ARGS[@]}" -n kube-system delete ingress ingress-dashboard --ignore-not-found >/dev/null
else
    DASHBOARD_NAMESPACE=kube-system
    DASHBOARD_SERVICE=kubernetes-dashboard
fi

"${KUBECTL_ARGS[@]}" -n "$DASHBOARD_NAMESPACE" create secret tls kubernetes-dashboard-tls \
    --cert="$SERVER_CERT" --key="$SERVER_KEY" --dry-run=client -o yaml \
  | "${KUBECTL_ARGS[@]}" apply -f - >/dev/null

export DASHBOARD_HOST DASHBOARD_NAMESPACE DASHBOARD_SERVICE
# Only substitute the named placeholder; single quotes intentionally keep the
# calling shell from expanding it before envsubst reads the template.
# shellcheck disable=SC2016
envsubst '${DASHBOARD_HOST} ${DASHBOARD_NAMESPACE} ${DASHBOARD_SERVICE}' < "$CURRENT_DIR/dashboard.yaml" \
  | "${KUBECTL_ARGS[@]}" apply -f - >/dev/null
fortify_annotate_traefik_https_service "$DASHBOARD_NAMESPACE" "$DASHBOARD_SERVICE" >/dev/null

if [ "$DASHBOARD_NAMESPACE" = kubernetes-dashboard ]; then
    "${KUBECTL_ARGS[@]}" -n "$DASHBOARD_NAMESPACE" rollout status deployment \
        -l app.kubernetes.io/instance=kubernetes-dashboard --timeout=300s
else
    "${KUBECTL_ARGS[@]}" -n "$DASHBOARD_NAMESPACE" rollout status deployment/kubernetes-dashboard --timeout=300s
fi
"${KUBECTL_ARGS[@]}" -n "$DASHBOARD_NAMESPACE" get service "$DASHBOARD_SERVICE" >/dev/null
"${KUBECTL_ARGS[@]}" -n "$DASHBOARD_NAMESPACE" get ingress ingress-dashboard >/dev/null

printf 'Dashboard ready: https://%s\n' "$DASHBOARD_HOST"
printf 'Generate a short-lived login token from the wizard when access is needed.\n'
