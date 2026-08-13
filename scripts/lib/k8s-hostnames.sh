#!/usr/bin/env bash

# Validate hostnames before handing them to Kubernetes Ingress. Kubernetes uses
# lowercase RFC 1123 subdomains for ingress hosts, so fail before Helm/apply can
# partially deploy a component with an invalid local .env value.

fortify_is_k8s_hostname() {
    local host="${1:-}"
    [ ${#host} -le 253 ] || return 1
    [[ "$host" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$ ]] || return 1
    [[ "$host" == *.* ]]
}

fortify_require_k8s_hostname() {
    local variable="$1" host="${2:-}"
    if fortify_is_k8s_hostname "$host"; then
        return 0
    fi
    printf 'Invalid %s for Kubernetes ingress: %s
' "$variable" "${host:-<unset>}" >&2
    printf 'Use a lowercase DNS name such as ssc.fortifydemo.com. Update .env through the Configuration editor, then retry.
' >&2
    return 1
}
