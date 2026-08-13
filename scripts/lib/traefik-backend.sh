#!/bin/bash

# MicroK8s 1.35+ backs the ingress addon with Traefik. Fortify services
# terminate HTTPS inside the pod with lab-generated/self-signed certs, so
# Traefik needs a ServersTransport when it forwards to those HTTPS backends.

fortify_traefik_kubectl_args() {
    read -r -a FORTIFY_TRAEFIK_KUBECTL_ARGS <<< "${KUBECTL_CMD:-microk8s kubectl}"
}

fortify_traefik_crd_available() {
    local crd="$1"
    fortify_traefik_kubectl_args
    "${FORTIFY_TRAEFIK_KUBECTL_ARGS[@]}" get crd "$crd" >/dev/null 2>&1
}

fortify_traefik_backend_transport_ref() {
    local namespace="$1" name="${FORTIFY_TRAEFIK_BACKEND_TRANSPORT_NAME:-fortify-insecure-backend}"
    printf '%s-%s@kubernetescrd' "$namespace" "$name"
}

fortify_apply_traefik_backend_transport() {
    local namespace="$1" name="${FORTIFY_TRAEFIK_BACKEND_TRANSPORT_NAME:-fortify-insecure-backend}"
    fortify_traefik_crd_available serverstransports.traefik.io || return 0
    fortify_traefik_kubectl_args
    cat <<YAML | "${FORTIFY_TRAEFIK_KUBECTL_ARGS[@]}" -n "$namespace" apply -f -
apiVersion: traefik.io/v1alpha1
kind: ServersTransport
metadata:
  name: ${name}
  namespace: ${namespace}
spec:
  insecureSkipVerify: true
YAML
}

fortify_annotate_traefik_https_service() {
    local namespace="$1" service="$2" transport_ref
    fortify_traefik_kubectl_args
    "${FORTIFY_TRAEFIK_KUBECTL_ARGS[@]}" -n "$namespace" get service "$service" >/dev/null 2>&1 || return 0
    fortify_traefik_crd_available serverstransports.traefik.io || return 0
    fortify_apply_traefik_backend_transport "$namespace"
    transport_ref="$(fortify_traefik_backend_transport_ref "$namespace")"
    "${FORTIFY_TRAEFIK_KUBECTL_ARGS[@]}" -n "$namespace" annotate service "$service" \
        traefik.ingress.kubernetes.io/service.serversscheme=https \
        traefik.ingress.kubernetes.io/service.serverstransport="$transport_ref" \
        --overwrite
}

fortify_delete_traefik_backend_transport() {
    local namespace="$1" name="${FORTIFY_TRAEFIK_BACKEND_TRANSPORT_NAME:-fortify-insecure-backend}"
    fortify_traefik_crd_available serverstransports.traefik.io || return 0
    fortify_traefik_kubectl_args
    "${FORTIFY_TRAEFIK_KUBECTL_ARGS[@]}" -n "$namespace" delete serverstransport.traefik.io "$name" --ignore-not-found
}
