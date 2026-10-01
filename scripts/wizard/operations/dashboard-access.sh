# shellcheck shell=bash
# Module: operations/dashboard-access
# Responsibility: Kubernetes Dashboard access, persistent token management, and access provisioning.
# Requires: kubectl, cluster status helpers, UI helpers
# Exports: dashboard_access_menu, dashboard_wait_for_persistent_token, dashboard_persistent_token, dashboard_revoke_persistent_tokens, dashboard_access_namespace, ensure_dashboard_access
# Side effects: May deploy Dashboard access resources and create or revoke access tokens.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_DASHBOARD_ACCESS_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_DASHBOARD_ACCESS_LOADED=1

dashboard_access_menu() {
    local dashboard_namespace
    while true; do
        title "Kubernetes Dashboard access"
        cat <<EOF

  URL: https://dashboard.$DOMAIN

  One-hour tokens are recommended. Persistent tokens remain valid until revoked
  or their service account is removed.

  1. Generate 1-hour view-only token (recommended)
  2. Generate 1-hour administrator token
  3. Generate persistent view-only token
  4. Generate persistent administrator token
  5. Revoke persistent Dashboard tokens

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1)
                section "View-only token (expires in 1 hour)"
                ensure_dashboard_access || { press_any; continue; }
                dashboard_namespace=$(dashboard_access_namespace)
                $KUBECTL -n "$dashboard_namespace" create token fortify-dashboard-viewer --duration=1h \
                    || error "Could not generate the Dashboard token"
                press_any
                ;;
            2)
                cat <<EOF

  WARNING: administrator access can modify or delete every workload,
  Secret, and persistent resource in this cluster.

EOF
                if confirm "Generate a 1-hour cluster administrator token?"; then
                    fortify_lab_show_action_warning admin-token
                    section "Administrator token (expires in 1 hour)"
                    ensure_dashboard_access || { press_any; continue; }
                    dashboard_namespace=$(dashboard_access_namespace)
                    $KUBECTL -n "$dashboard_namespace" create token fortify-dashboard-admin --duration=1h \
                        || error "Could not generate the Dashboard token"
                    press_any
                fi
                ;;
            3)
                dashboard_persistent_token viewer
                press_any
                ;;
            4)
                dashboard_persistent_token admin
                press_any
                ;;
            5)
                if confirm "Revoke every persistent Dashboard token?"; then
                    dashboard_revoke_persistent_tokens
                fi
                press_any
                ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

dashboard_wait_for_persistent_token() {
    local dashboard_namespace="$1" secret_name="$2"
    local timeout_seconds="${DASHBOARD_TOKEN_WAIT_SECONDS:-30}" started=$SECONDS
    [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || {
        error "Dashboard token wait must be a positive number of seconds."
        return 1
    }
    while [ $((SECONDS - started)) -lt "$timeout_seconds" ]; do
        if $KUBECTL -n "$dashboard_namespace" get secret "$secret_name" \
            -o jsonpath='{.data.token}' 2>/dev/null | grep -q .; then
            return 0
        fi
        sleep 1
    done
    error "Kubernetes did not populate the persistent Dashboard token within ${timeout_seconds}s."
    return 1
}

dashboard_persistent_token() {
    local access="$1" dashboard_namespace service_account secret_name confirmation
    case "$access" in
        viewer)
            service_account=fortify-dashboard-viewer
            secret_name=fortify-dashboard-viewer-persistent-token
            ;;
        admin)
            service_account=fortify-dashboard-admin
            secret_name=fortify-dashboard-admin-persistent-token
            ;;
        *) error "Unknown Dashboard access level."; return 2 ;;
    esac

    cat <<EOF

  PERSISTENT TOKEN WARNING
  This bearer token does not expire automatically. Anyone who obtains it has
  ${access} access to the lab cluster until the token is revoked. It is stored
  only as a Kubernetes Secret; do not save it in Git, .env, logs, or chat.

EOF
    if [ "$access" = admin ]; then
        fortify_lab_show_action_warning admin-token
        ask confirmation "Type PERSISTENT to create a non-expiring administrator token:"
        [ "$confirmation" = PERSISTENT ] || { note "Persistent administrator token cancelled."; return; }
    elif ! confirm "Create a persistent view-only token?"; then
        return
    fi

    ensure_dashboard_access || return 1
    dashboard_namespace=$(dashboard_access_namespace)
    if ! $KUBECTL apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $secret_name
  namespace: $dashboard_namespace
  annotations:
    kubernetes.io/service-account.name: $service_account
type: kubernetes.io/service-account-token
EOF
    then
        error "Could not create the persistent Dashboard token Secret."
        return 1
    fi
    dashboard_wait_for_persistent_token "$dashboard_namespace" "$secret_name" || return 1
    section "Persistent ${access} token (valid until revoked)"
    if ! $KUBECTL -n "$dashboard_namespace" get secret "$secret_name" \
        -o jsonpath='{.data.token}' | base64 -d; then
        error "Could not retrieve the persistent Dashboard token."
        return 1
    fi
    echo
    note "Use Dashboard access option 5 to revoke this token."
}

dashboard_revoke_persistent_tokens() {
    local dashboard_namespace
    dashboard_namespace=$(dashboard_access_namespace)
    $KUBECTL -n "$dashboard_namespace" delete secret \
        fortify-dashboard-viewer-persistent-token \
        fortify-dashboard-admin-persistent-token \
        --ignore-not-found >/dev/null || {
        error "Could not revoke the persistent Dashboard tokens."
        return 1
    }
    note "Persistent Dashboard tokens revoked. Existing one-hour tokens are unaffected."
}

dashboard_access_namespace() {
    if $KUBECTL -n kubernetes-dashboard get service kubernetes-dashboard-kong-proxy >/dev/null 2>&1; then
        printf '%s\n' kubernetes-dashboard
    else
        printf '%s\n' kube-system
    fi
}

ensure_dashboard_access() {
    local resource dashboard_namespace dashboard_service
    dashboard_namespace=$(dashboard_access_namespace)
    if [ "$dashboard_namespace" = kubernetes-dashboard ]; then
        dashboard_service=kubernetes-dashboard-kong-proxy
    else
        dashboard_service=kubernetes-dashboard
    fi
    for resource in \
        "service/$dashboard_service" \
        serviceaccount/fortify-dashboard-viewer \
        serviceaccount/fortify-dashboard-admin \
        ingress/ingress-dashboard; do
        if ! $KUBECTL -n "$dashboard_namespace" get "$resource" >/dev/null 2>&1; then
            note "Dashboard access is incomplete; repairing the idempotent Dashboard deployment."
            if ! bash "$FORTIFY_HOME_K8S/apps/kubernetes-dashboard/deploy.sh"; then
                error "Dashboard repair failed. Review the error above, then retry."
                return 1
            fi
            break
        fi
    done

    dashboard_namespace=$(dashboard_access_namespace)
    if [ "$dashboard_namespace" = kubernetes-dashboard ]; then
        dashboard_service=kubernetes-dashboard-kong-proxy
    else
        dashboard_service=kubernetes-dashboard
    fi
    for resource in \
        "service/$dashboard_service" \
        serviceaccount/fortify-dashboard-viewer \
        serviceaccount/fortify-dashboard-admin \
        ingress/ingress-dashboard; do
        if ! $KUBECTL -n "$dashboard_namespace" get "$resource" >/dev/null 2>&1; then
            error "Dashboard repair completed without $resource; token generation is blocked."
            return 1
        fi
    done
}
