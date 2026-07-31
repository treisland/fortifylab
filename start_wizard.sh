#!/bin/bash
# start_wizard.sh — Fortify Lab management wizard
#
# Interactive menu for deploying, configuring, and operating the
# Fortify Helm-based lab. Run as your normal user (not root). The
# wizard sudo's only commands that genuinely need it (apt, snap).
# Cluster ops use plain kubectl/helm — no sudo needed when you're
# in the microk8s group.

set -o pipefail


# ============================================================
# Locate FORTIFY_HOME_K8S, source .env
# ============================================================

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export FORTIFY_HOME_K8S
fi

ENV_FILE="$FORTIFY_HOME_K8S/.env"
ENV_EXAMPLE="$FORTIFY_HOME_K8S/.env.example"


# ============================================================
# Visual helpers (respect NO_COLOR)
# ============================================================

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD="$(tput bold 2>/dev/null || true)"
    DIM="$(tput dim 2>/dev/null || true)"
    RED="$(tput setaf 1 2>/dev/null || true)"
    GREEN="$(tput setaf 2 2>/dev/null || true)"
    YELLOW="$(tput setaf 3 2>/dev/null || true)"
    BLUE="$(tput setaf 4 2>/dev/null || true)"
    RESET="$(tput sgr0 2>/dev/null || true)"
else
    BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
fi

OK_MARK="${GREEN}✓${RESET}"
WARN_MARK="${YELLOW}⚠${RESET}"
FAIL_MARK="${RED}✗${RESET}"
INFO_MARK="${BLUE}ℹ${RESET}"

hr()       { printf '%s\n' "────────────────────────────────────────────────────────────"; }
title()    { clear; printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; hr; }
section()  { printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; }
press_any(){ printf '\n'; read -rp "Press Enter to continue... " _; }
ask()      { local _v="$1"; shift; read -rp "$* " "$_v"; }
confirm()  { local r; read -rp "$1 [y/N] " r; [[ "$r" =~ ^[Yy]$ ]]; }
error()    { printf '%s %s\n' "$FAIL_MARK" "$*" >&2; }
note()     { printf '%s %s\n' "$INFO_MARK" "$*"; }

# shellcheck source=scripts/lib/help.sh
source "$FORTIFY_HOME_K8S/scripts/lib/help.sh"
# shellcheck source=scripts/lib/lab-disclaimer.sh
source "$FORTIFY_HOME_K8S/scripts/lib/lab-disclaimer.sh"
# shellcheck source=scripts/lib/operational-help.sh
source "$FORTIFY_HOME_K8S/scripts/lib/operational-help.sh"


# ============================================================
# Cluster CLI detection (microk8s vs upstream)
# ============================================================

if command -v microk8s &>/dev/null; then
    KUBECTL="microk8s kubectl"
    HELM="microk8s helm"
elif command -v kubectl &>/dev/null; then
    KUBECTL="kubectl"
    HELM="helm"
else
    KUBECTL=""
    HELM=""
fi
[ -n "$KUBECTL" ] && FORTIFY_OPERATION_KUBECTL="$KUBECTL"


# ============================================================
# Source .env (creates from .env.example on first run)
# ============================================================

bootstrap_env() {
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            note "Created $ENV_FILE from .env.example."
            note "Edit it (option 13) to set your domain, passwords, and image versions."
            press_any
        else
            error "Neither .env nor .env.example found in $FORTIFY_HOME_K8S."
            exit 1
        fi
    fi
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    FORTIFY_OPERATION_NAMESPACE="${NAMESPACE:-fortify}"
}


# ============================================================
# App registry — single source of truth for the apps menu
# ============================================================

APP_LABEL=("MySQL" "PostgreSQL" "SSC" "LIM" "ScanCentral SAST" "ScanCentral DAST")
APP_PODS=("mysql"  "postgresql" "ssc-webapp" "lim" "scancentral-sast" "sdast")
APP_URL_VAR=(""    ""           "SSC_URL"    "LIM_URL" "SCSAST_CTRL_URL" "SCDAST_URL")
APP_START=(
    "apps/mysql/start.sh"
    "apps/postgresql/start.sh"
    "apps/ssc/start.sh"
    "apps/lim/start.sh"
    "apps/scsast/start.sh"
    "apps/scdast/core/start.sh apps/scdast/scanner/start.sh"
)
APP_STOP=(
    "apps/mysql/stop.sh"
    "apps/postgresql/stop.sh"
    "apps/ssc/stop.sh"
    "apps/lim/stop.sh"
    "apps/scsast/stop.sh"
    "apps/scdast/core/stop.sh apps/scdast/scanner/stop.sh"
)
APP_DESTROY=(
    "apps/mysql/destroy.sh"
    "apps/postgresql/destroy.sh"
    "apps/ssc/destroy.sh"
    "apps/lim/destroy.sh"
    "apps/scsast/destroy.sh"
    "apps/scdast/core/destroy.sh apps/scdast/scanner/destroy.sh"
)


# ============================================================
# Status checks (cheap; called every menu render)
# ============================================================

cluster_reachable() { [ -n "$KUBECTL" ] && $KUBECTL cluster-info &>/dev/null; }

status_prereqs() {
    local missing=()
    command -v java     &>/dev/null || missing+=("java")
    command -v docker   &>/dev/null || missing+=("docker")
    command -v microk8s &>/dev/null || missing+=("microk8s")
    command -v mkcert   &>/dev/null || missing+=("mkcert")
    if [ ${#missing[@]} -eq 0 ]; then
        printf '%s Prerequisites installed\n' "$OK_MARK"
    else
        printf '%s Prerequisites missing: %s\n' "$FAIL_MARK" "${missing[*]}"
    fi
}

status_license() {
    if ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
         fortify_resolve_license_file ) 2>/dev/null; then
        printf '%s License file present\n' "$OK_MARK"
    else
        printf '%s License missing — option 4 to add\n' "$FAIL_MARK"
    fi
}

status_cluster() {
    if ! cluster_reachable; then
        printf '%s Cluster not reachable\n' "$FAIL_MARK"
        return
    fi
    local total ready
    total=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null | wc -l)
    if [ "$total" -eq 0 ]; then
        printf '%s Cluster up, no pods deployed yet\n' "$WARN_MARK"
        return
    fi
    ready=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
        | awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}')
    if [ "$ready" -eq "$total" ]; then
        printf '%s Cluster: %d/%d pods ready\n' "$OK_MARK" "$ready" "$total"
    else
        printf '%s Cluster: %d/%d pods ready\n' "$WARN_MARK" "$ready" "$total"
    fi
}

status_user() {
    if [ "$(id -u)" -eq 0 ] || [ -n "${SUDO_USER:-}" ]; then
        printf '%s Running as root/sudo — mkcert and helm should run as your normal user\n' "$WARN_MARK"
    fi
}


# ============================================================
# Per-app helpers
# ============================================================

# Aggregate status for one app (e.g. "3/3 ready" or "0/0 not deployed").
app_status() {
    local prefix="$1" total ready
    local pods
    pods=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
           | awk -v p="$prefix" '$1 ~ "^"p {print}')
    if [ -z "$pods" ]; then
        printf '%snot deployed%s' "$DIM" "$RESET"
        return
    fi
    total=$(echo "$pods" | wc -l)
    ready=$(echo "$pods" | awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}')
    if [ "$ready" -eq "$total" ]; then
        printf '%s%d/%d running%s' "$GREEN" "$ready" "$total" "$RESET"
    else
        printf '%s%d/%d ready%s' "$YELLOW" "$ready" "$total" "$RESET"
    fi
}

# Run a (possibly multi-) script field from APP_START/STOP/DESTROY.
run_app_scripts() {
    local field="$1" script
    for script in $field; do
        if [ ! -f "$FORTIFY_HOME_K8S/$script" ]; then
            error "Missing $script"
            return 1
        fi
        bash "$FORTIFY_HOME_K8S/$script" || return $?
    done
}


# ============================================================
# Apps submenu
# ============================================================

apps_menu() {
    while true; do
        title "Apps"
        printf '\n  %-3s %-20s %s\n' "#" "Name" "Status"
        printf '  %s\n' "─────────────────────────────────────"
        local i
        for i in "${!APP_LABEL[@]}"; do
            printf '  %-3d %-20s %s\n' \
                $((i + 1)) "${APP_LABEL[$i]}" "$(app_status "${APP_PODS[$i]}")"
        done
        echo
        echo "  r. Return to main menu"
        echo "  q. Quit"
        echo
        ask choice "Select an app:"

        case "$choice" in
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            ''|*[!0-9]*) error "Invalid selection"; sleep 1 ;;
            *)
                if [ "$choice" -ge 1 ] && [ "$choice" -le "${#APP_LABEL[@]}" ]; then
                    app_action_menu $((choice - 1))
                else
                    error "Out of range"
                    sleep 1
                fi
                ;;
        esac
    done
}

app_action_menu() {
    local idx="$1"
    while true; do
        title "${APP_LABEL[$idx]}"
        local url=""
        [ -n "${APP_URL_VAR[$idx]}" ] && url="${!APP_URL_VAR[$idx]:-}"

        echo
        printf '  Status: %s\n' "$(app_status "${APP_PODS[$idx]}")"
        [ -n "$url" ] && printf '  URL:    %s\n' "$url"
        echo

        echo "  1. Start / Upgrade"
        echo "  2. Stop"
        echo "  3. Destroy (deletes data)"
        echo "  4. Logs"
        echo "  5. Show URL & credentials"
        case "${APP_LABEL[$idx]}" in
            "ScanCentral SAST"|"ScanCentral DAST")
                echo "  6. Scale workers"
                ;;
        esac
        echo
        echo "  r. Return"
        echo "  q. Quit"
        echo
        ask choice "Select:"

        case "$choice" in
            1)
                run_app_scripts "${APP_START[$idx]}"
                press_any ;;
            2)
                run_app_scripts "${APP_STOP[$idx]}"
                press_any ;;
            3)
                fortify_lab_show_action_warning destructive
                if confirm "DELETE ${APP_LABEL[$idx]} and its data. Continue?"; then
                    run_app_scripts "${APP_DESTROY[$idx]}"
                fi
                press_any ;;
            4) logs_for_prefix "${APP_PODS[$idx]}" ;;
            5) show_app_creds "$idx"; press_any ;;
            6) scale_workers "$idx"; press_any ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

scale_workers() {
    local idx="$1" sts replicas
    case "${APP_LABEL[$idx]}" in
        "ScanCentral SAST") sts="scancentral-sast-worker-linux" ;;
        "ScanCentral DAST") sts="sdast-scanner-scancentral-dast-scanner" ;;
        *) error "Scaling not supported for ${APP_LABEL[$idx]}"; return ;;
    esac
    local current
    current=$($KUBECTL -n "$NAMESPACE" get statefulset "$sts" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
    note "Current $sts replicas: $current"
    ask replicas "New replica count (or empty to cancel):"
    [ -z "$replicas" ] && return
    [[ "$replicas" =~ ^[0-9]+$ ]] || { error "Not a number"; return; }
    $KUBECTL -n "$NAMESPACE" scale statefulset "$sts" --replicas="$replicas"
}

show_app_creds() {
    local idx="$1" url=""
    [ -n "${APP_URL_VAR[$idx]}" ] && url="${!APP_URL_VAR[$idx]:-}"
    section "${APP_LABEL[$idx]}"
    [ -n "$url" ] && printf '  URL: %s\n' "$url"
    case "${APP_LABEL[$idx]}" in
        SSC)
            echo "  Login: see SSC startup logs for the initial admin password"
            echo "         (option 4 → SSC, search the log for 'admin')"
            ;;
        LIM)
            echo "  Login username: lim_admin"
            echo "  Password: use the configured lab default password (not displayed)"
            ;;
        "ScanCentral SAST")
            echo "  Controller URL: $url"
            echo "  Generate the controller token from SSC and apply via option 6 (Configure)."
            ;;
        "ScanCentral DAST")
            echo "  API URL: ${SCDAST_API_URL:-<unset>}"
            ;;
    esac
}


# ============================================================
# License menu
# ============================================================

license_menu() {
    while true; do
        title "License files"
        local default_file="$FORTIFY_HOME_K8S/secrets/input/fortify.license"
        echo
        if ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
             fortify_resolve_license_file ) 2>/dev/null; then
            printf '  %s Configured Fortify license is readable\n' "$OK_MARK"
        else
            printf '  %s Configured Fortify license is unavailable\n' "$FAIL_MARK"
        fi
        echo
        echo "  1. Import to the backward-compatible repository-local location"
        echo "  2. Where to obtain a license"
        echo
        echo "  r. Return"
        echo
        ask choice "Select:"

        case "$choice" in
            1)
                ask src "Path to fortify.license file:"
                if [ ! -s "$src" ]; then
                    error "The selected file is missing, unreadable, or empty."
                else
                    mkdir -p "$(dirname "$default_file")"
                    cp "$src" "$default_file" && note "Imported license file."
                fi
                press_any ;;
            2)
                cat <<EOF

  Customers: download from your OpenText / Fortify customer portal.
  Trial:     request at https://www.opentext.com/products/fortify

  Set FORTIFY_LICENSE_FILE in .env to keep the file outside this repository,
  or use option 1 for the backward-compatible gitignored location.

EOF
                press_any ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


# ============================================================
# Certs + Secrets generation
# ============================================================

certs_secrets_menu() {
    title "Generate certs + secrets"
    cat <<EOF

  This rebuilds the lab's TLS chain and recreates every k8s Secret
  in the '$NAMESPACE' namespace.

  WARNING: rebuilding rotates SSC's secret.key, which invalidates any
  encrypted credentials already stored in the SSC database. Only run
  this on a fresh deploy or immediately before destroying SSC's data.

EOF
    echo "  1. Run scripts/create-certs.sh"
    echo "  2. Run scripts/create-secrets.sh"
    echo "  3. Run both (in order)"
    echo
    echo "  r. Return"
    echo
    ask choice "Select:"

    case "$choice" in
        1) ( bash "$FORTIFY_HOME_K8S/scripts/create-certs.sh" );        press_any ;;
        2) ( bash "$FORTIFY_HOME_K8S/scripts/create-secrets.sh" );      press_any ;;
        3) ( bash "$FORTIFY_HOME_K8S/scripts/create-certs.sh" \
             && bash "$FORTIFY_HOME_K8S/scripts/create-secrets.sh" );   press_any ;;
        [Rr]) return ;;
        *) error "Invalid"; sleep 1 ;;
    esac
}


# ============================================================
# Configure: DNS, SSC token, LIM license, rulepack cert refresh
# ============================================================

configure_menu() {
    while true; do
        title "Configure"
        cat <<EOF

  1. DNS — print /etc/hosts entries + apply CoreDNS hosts override
  2. Apply SSC ControllerToken to ScanCentral SAST
  3. LIM — DAST license & default pool (manual instructions)
  4. Refresh update.fortify.com cert in truststore
  5. Kubernetes Dashboard access

  r. Return
EOF
        echo
        ask choice "Select:"

        case "$choice" in
            1) configure_dns;        press_any ;;
            2) configure_ssc_token;  press_any ;;
            3) configure_lim;        press_any ;;
            4) refresh_rules_cert;   press_any ;;
            5) dashboard_access_menu ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

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

configure_dns() {
    local ip
    ip=$(hostname -I | awk '{print $1}')
    cat <<EOF

  ── Client side ─────────────────────────────────────────
  Add to your client's /etc/hosts (or Pi-hole DNS):

    $ip   ssc.$DOMAIN sast.$DOMAIN dast.$DOMAIN lim.$DOMAIN dashboard.$DOMAIN

  ── In-cluster side ─────────────────────────────────────
  Pods inside the cluster need to resolve $DOMAIN themselves
  (e.g. SCDAST scanner calls https://dast.$DOMAIN). We patch
  CoreDNS's hosts plugin so they resolve to this node's IP.

EOF
    if confirm "Apply CoreDNS hosts override now?"; then
        local cm
        cm=$($KUBECTL -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}' 2>/dev/null)
        if [ -z "$cm" ]; then
            error "Could not read coredns ConfigMap"
            return
        fi
        if echo "$cm" | grep -q "$DOMAIN"; then
            note "CoreDNS already has an entry for $DOMAIN — skipping."
            return
        fi
        # Insert a hosts block before the closing brace of the .:53 server block.
        local patched
        patched=$(echo "$cm" | awk -v ip="$ip" -v dom="$DOMAIN" '
            /^}/ && !done { print "    hosts {"; print "        " ip " ssc." dom " sast." dom " dast." dom " lim." dom " dashboard." dom; print "        fallthrough"; print "    }"; done=1 } { print }')
        $KUBECTL -n kube-system create configmap coredns \
            --from-literal=Corefile="$patched" --dry-run=client -o yaml \
          | $KUBECTL -n kube-system apply -f - >/dev/null
        $KUBECTL -n kube-system rollout restart deployment/coredns >/dev/null
        note "CoreDNS patched and restarted."
    fi
}

configure_ssc_token() {
    local token encoded_token
    cat <<EOF

  In SSC: Administration → ScanCentral SAST → Tokens →
          Create token of type 'ScanCentralCtrlToken'.
          Copy the value below.

EOF
    read -rsp "Paste ControllerToken (input hidden; empty cancels): " token
    echo
    [ -z "$token" ] && return
    if ! $HELM -n "$NAMESPACE" status scancentral-sast &>/dev/null; then
        error "ScanCentral SAST is not deployed yet."
        return
    fi
    encoded_token=$(printf '%s' "$token" | base64 | tr -d '\n')
    token=""
    if ! printf '{"metadata":{"annotations":{"fortify.dev/ssc-controller-token-configured":"true"}},"data":{"scancentral-ssc-scancentral-ctrl-secret":"%s"}}\n' \
        "$encoded_token" | $KUBECTL -n "$NAMESPACE" patch secret fortify-secrets \
        --type=merge --patch-file /dev/stdin >/dev/null; then
        encoded_token=""
        error "Could not update the protected ScanCentral SSC credential."
        return 1
    fi
    encoded_token=""
    if ! $HELM -n "$NAMESPACE" upgrade scancentral-sast \
        oci://registry-1.docker.io/fortifydocker/helm-scancentral-sast \
        --version "$FORTIFY_SCSAST_CHART_VERSION" --reuse-values \
        --set-string controller.sscScanCentralCtrlToken= \
        --set-string secrets.fortifyLicense= \
        --set-string secrets.workerAuthToken= \
        --set-string secrets.clientAuthToken= \
        --set-string secrets.sscScanCentralCtrlSecret= >/dev/null; then
        error "The Secret was updated, but legacy token metadata could not be cleared from the Helm release."
        return 1
    fi
    $KUBECTL -n "$NAMESPACE" rollout restart statefulset/scancentral-sast-controller >/dev/null
    if ! $KUBECTL -n "$NAMESPACE" rollout status statefulset/scancentral-sast-controller --timeout=300s; then
        error "The token was updated, but the SAST controller did not become ready."
        return 1
    fi
    note "ControllerToken updated without placing it in terminal output, process arguments, files, or Helm values."
}

configure_lim() {
    cat <<EOF

  LIM needs a DAST license file uploaded and a Default scanner pool
  configured before SCDAST can run scans. Both steps are done in
  LIM's web UI:

    1. Open ${LIM_URL:-https://lim.$DOMAIN}
    2. Sign in as lim_admin using the configured lab default password.
       The wizard deliberately does not display passwords.
    3. Upload your DAST license file.
    4. Create a pool named 'Default' (matches \$LIM_POOL_NAME in .env).
    5. Generate seats / activate as documented by Fortify.

  After that, redeploy SCDAST (Apps → ScanCentral DAST → Start/Upgrade)
  so the scanner can authenticate to LIM.

EOF
}

refresh_rules_cert() {
    cat <<EOF

  Re-imports the current update.fortify.com leaf and root CA into the
  truststore. Run this when SSC reports a PKIX/handshake error fetching
  rulepacks (typically every 13 months when the leaf rotates).

EOF
    confirm "Refresh now?" || return

    local update_chain root_ca
    update_chain=$(mktemp)
    root_ca=$(mktemp)

    openssl s_client -servername "$FORTIFY_RULES_DOMAIN" \
        -connect "$FORTIFY_RULES_DOMAIN":443 -showcerts </dev/null 2>/dev/null \
      | awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > "$update_chain"

    awk -v last="$(grep -c '^-----BEGIN CERTIFICATE-----' "$update_chain")" '
        /-----BEGIN CERTIFICATE-----/{c++}
        c==last' "$update_chain" > "$root_ca"

    keytool -delete -alias update-fortify-root-ca -keystore "$TRUSTSTORE" \
        -storepass "$DEFAULT_PASS" 2>/dev/null || true
    keytool -import -alias update-fortify-root-ca -file "$root_ca" \
        -keystore "$TRUSTSTORE" -storepass "$DEFAULT_PASS" -noprompt

    rm -f "$update_chain" "$root_ca"

    # Push back into the live secret + restart SSC.
    $KUBECTL -n "$NAMESPACE" patch secret fortify-secrets \
        --type=merge -p "{\"data\":{\"truststore\":\"$(base64 -w0 < "$TRUSTSTORE")\"}}"
    $KUBECTL -n "$NAMESPACE" delete pod ssc-webapp-0 --ignore-not-found
    note "Truststore refreshed; SSC restarting."
}


# ============================================================
# Operations: status, logs, urls, versions
# ============================================================

cluster_status() {
    title "Cluster status"
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    section "Pods (namespace: $NAMESPACE)"
    $KUBECTL -n "$NAMESPACE" get pods 2>/dev/null
    section "Pods not Ready"
    local issues
    issues=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
        | awk '$3 != "Running" || ($2 ~ /^[0-9]+\/[0-9]+$/ && split($2,a,"/") && a[1] != a[2])')
    if [ -z "$issues" ]; then
        echo "  (none)"
    else
        echo "$issues"
    fi
    press_any
}

# Auto-refreshing dashboard. Uses our existing status helpers + per-app
# rows; trapped Ctrl+C exits cleanly back to the menu.
live_status() {
    local interval="${1:-5}"
    trap 'live_status_running=0' INT
    live_status_running=1

    while [ "$live_status_running" -eq 1 ]; do
        clear
        printf '%sFortify Lab — Live Status%s   refresh %ss   Ctrl+C to exit\n' \
            "$BOLD" "$RESET" "$interval"
        printf '%s%s%s\n' "$DIM" "$(date '+%Y-%m-%d %H:%M:%S')" "$RESET"
        hr

        section "Cluster"
        printf '  %s\n' "$(status_cluster)"

        if cluster_reachable; then
            section "Apps"
            local i pods total ready issues
            for i in "${!APP_LABEL[@]}"; do
                pods=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
                       | awk -v p="${APP_PODS[$i]}" '$1 ~ "^"p {print}')
                if [ -z "$pods" ]; then
                    printf '  %-20s %snot deployed%s\n' "${APP_LABEL[$i]}" "$DIM" "$RESET"
                    continue
                fi
                total=$(echo "$pods" | wc -l)
                ready=$(echo "$pods" | awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}')
                if [ "$ready" -eq "$total" ]; then
                    printf '  %-20s %s%d/%d running%s\n' \
                        "${APP_LABEL[$i]}" "$GREEN" "$ready" "$total" "$RESET"
                else
                    printf '  %-20s %s%d/%d ready%s\n' \
                        "${APP_LABEL[$i]}" "$YELLOW" "$ready" "$total" "$RESET"
                    # Show offenders inline so the user sees why
                    echo "$pods" | awk '$3!="Running" || ($2 ~ /^[0-9]+\/[0-9]+$/ && split($2,a,"/") && a[1]!=a[2]) { printf "    %s%s%s  %s  %s\n", "'"$DIM"'", $1, "'"$RESET"'", $2, $3 }'
                fi
            done

            section "Recent events (last 8)"
            $KUBECTL -n "$NAMESPACE" get events --sort-by='.lastTimestamp' 2>/dev/null \
              | tail -8 \
              | awk 'NR>0 { printf "  %s\n", $0 }'
        fi

        # Sleep responsively so Ctrl+C exits within ~1s.
        local elapsed=0
        while [ "$elapsed" -lt "$interval" ] && [ "$live_status_running" -eq 1 ]; do
            sleep 1
            elapsed=$((elapsed + 1))
        done
    done

    trap - INT
    clear
}

logs_menu() {
    title "Pod logs"
    local pods=()
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    mapfile -t pods < <($KUBECTL -n "$NAMESPACE" get pods -o name 2>/dev/null | sed 's|^pod/||')
    if [ ${#pods[@]} -eq 0 ]; then
        note "No pods in '$NAMESPACE'"
        press_any; return
    fi
    ask filter "Filter (substring, blank=all):"
    local matched=() i
    for i in "${!pods[@]}"; do
        if [ -z "$filter" ] || [[ "${pods[$i]}" == *"$filter"* ]]; then
            matched+=("${pods[$i]}")
        fi
    done
    if [ ${#matched[@]} -eq 0 ]; then
        note "No pods matched '$filter'"
        press_any; return
    fi
    echo
    for i in "${!matched[@]}"; do
        printf '  %2d. %s\n' $((i + 1)) "${matched[$i]}"
    done
    echo
    ask sel "Pod number:"
    [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -le ${#matched[@]} ] || {
        error "Invalid"; press_any; return
    }
    local pod="${matched[$((sel-1))]}"
    if confirm "Follow logs (Ctrl+C to exit)?"; then
        $KUBECTL -n "$NAMESPACE" logs --follow "$pod" || true
    else
        $KUBECTL -n "$NAMESPACE" logs --tail=200 "$pod" || true
        press_any
    fi
}

logs_for_prefix() {
    local prefix="$1" pods=() i
    mapfile -t pods < <($KUBECTL -n "$NAMESPACE" get pods -o name 2>/dev/null \
                       | sed 's|^pod/||' | grep "^$prefix")
    if [ ${#pods[@]} -eq 0 ]; then
        note "No pods matching '$prefix'"
        press_any; return
    fi
    if [ ${#pods[@]} -eq 1 ]; then
        $KUBECTL -n "$NAMESPACE" logs --tail=200 "${pods[0]}" || true
    else
        echo
        for i in "${!pods[@]}"; do
            printf '  %2d. %s\n' $((i + 1)) "${pods[$i]}"
        done
        ask sel "Pod number:"
        [[ "$sel" =~ ^[0-9]+$ ]] || return
        $KUBECTL -n "$NAMESPACE" logs --tail=200 "${pods[$((sel-1))]}" || true
    fi
    press_any
}

# Multi-pod log streamer. Tails every pod in $NAMESPACE in parallel,
# tagging each line with a colored [pod-name] prefix. Optional substring
# filter applies to the LINE, not the pod name (use logs_menu for that).
# Ctrl+C kills all backgrounded tails and returns to the menu.
stream_logs() {
    title "Stream logs (all pods)"
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    local pods=()
    mapfile -t pods < <($KUBECTL -n "$NAMESPACE" get pods -o name 2>/dev/null | sed 's|^pod/||')
    if [ ${#pods[@]} -eq 0 ]; then
        note "No pods in '$NAMESPACE'"
        press_any; return
    fi
    echo
    echo "  ${#pods[@]} pods will be tailed in parallel."
    echo "  Tip: filter to surface the lines you care about (errors, specific words)."
    echo
    ask filter "Line filter (substring, blank for all):"

    local pids=() pod color color_idx short
    # Cycle through 6 ANSI colors so adjacent pods read distinct.
    local colors=(1 2 3 4 5 6)

    # Each pod tail runs in a backgrounded subshell that traps its OWN
    # exit and does `kill 0` — sending TERM to its entire process group,
    # which includes all pipeline children (kubectl + grep + awk). That
    # way the parent's cleanup just has to TERM the subshells; each one
    # fans out its own kill. Without this, `( pipe1 | pipe2 ) &`
    # leaks the kubectl process when the subshell exits — which was the
    # bug the user hit when `source`-ing the wizard.
    cleanup_streams() {
        local p
        for p in "${pids[@]}"; do
            kill -TERM "$p" 2>/dev/null
        done
        # Brief grace, then verify clean.
        sleep 0.3
        for p in "${pids[@]}"; do
            wait "$p" 2>/dev/null
        done
        pids=()
    }
    trap 'cleanup_streams; trap - INT; echo; return 0' INT

    echo
    note "Streaming. Ctrl+C to stop."
    echo

    for i in "${!pods[@]}"; do
        pod="${pods[$i]}"
        color_idx="${colors[$((i % ${#colors[@]}))]}"
        if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
            color="$(tput setaf "$color_idx" 2>/dev/null || true)"
        else
            color=""
        fi
        short="$pod"

        if [ -n "$filter" ]; then
            (
              # On any exit, kill our entire process group → takes
              # down kubectl logs + grep + awk in one shot.
              trap 'kill 0' EXIT
              $KUBECTL -n "$NAMESPACE" logs --follow --all-containers --tail=20 \
                  --ignore-errors=true "$pod" 2>&1 \
              | grep --line-buffered -F -- "$filter" \
              | awk -v c="$color" -v r="$RESET" -v p="$short" \
                  '{ printf "%s[%s]%s %s\n", c, p, r, $0; fflush() }'
            ) &
        else
            (
              trap 'kill 0' EXIT
              $KUBECTL -n "$NAMESPACE" logs --follow --all-containers --tail=20 \
                  --ignore-errors=true "$pod" 2>&1 \
              | awk -v c="$color" -v r="$RESET" -v p="$short" \
                  '{ printf "%s[%s]%s %s\n", c, p, r, $0; fflush() }'
            ) &
        fi
        pids+=("$!")
    done

    # Block until all backgrounded tails exit OR Ctrl+C trips the trap.
    wait
    cleanup_streams
    trap - INT
}

urls_creds() {
    title "URLs & credentials"
    cat <<EOF

  SSC          ${SSC_URL:-<unset>}
                login: see initial admin password in SSC startup logs

  LIM          ${LIM_URL:-<unset>}
                login: lim_admin / configured lab password (not displayed)

  SAST ctrl    ${SCSAST_CTRL_URL:-<unset>}
                shared secret applied via Configure → option 2

  DAST API     ${SCDAST_URL:-<unset>}
                login: SSC user mapped to DAST role

  K8s dashboard https://dashboard.$DOMAIN
                access: Configure → Kubernetes Dashboard access

EOF
    press_any
}

versions_menu() {
    title "Image versions"
    section "Configured (.env)"
    grep -E '^\s*export\s+FORTIFY_.*(CHART_VERSION|IMAGE_TAG)=' "$ENV_FILE" \
        | sed 's/^\s*export\s*/  /'
    section "Running"
    if cluster_reachable; then
        $KUBECTL -n "$NAMESPACE" get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}' 2>/dev/null \
            | awk -F'\t' '{ printf "  %-50s %s\n", $1, $2 }'
    else
        note "(cluster unreachable)"
    fi
    press_any
}

edit_env() {
    "${EDITOR:-nano}" "$ENV_FILE"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
}


# ============================================================
# Prerequisites menu
# ============================================================

prereqs_menu() {
    while true; do
        title "Install prerequisites"
        echo
        echo "  1. JDK 17 (apt)"
        echo "  2. Docker (apt) + docker login"
        echo "  3. mkcert (apt)"
        echo "  4. microk8s (snap) + addons (dns, ingress, nfs, dashboard, community)"
        echo "  5. All of the above"
        echo
        echo "  r. Return"
        echo
        ask choice "Select:"

        case "$choice" in
            1) install_jdk;        press_any ;;
            2) install_docker;     press_any ;;
            3) install_mkcert;     press_any ;;
            4) install_microk8s;   press_any ;;
            5) install_jdk; install_docker; install_mkcert; install_microk8s; press_any ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

advanced_menu() {
    while true; do
        title "Advanced setup and configuration"
        cat <<EOF

  1. Install prerequisites
  2. License files
  3. Generate certificates and Secrets
  4. Configure DNS, SSC token, LIM, and Dashboard access
  5. Edit .env

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) prereqs_menu ;;
            2) license_menu ;;
            3) certs_secrets_menu ;;
            4) configure_menu ;;
            5) edit_env ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

operational_troubleshooting_menu() {
    local choice topic help_topic
    while true; do
        title "Troubleshooting assistant"
        cat <<'EOF'

  1. Deployment step failed       7. SSC
  2. Pod is Pending               8. ScanCentral SAST
  3. Pod is restarting            9. ScanCentral DAST
  4. URL does not open           10. Kubernetes Dashboard
  5. TLS warning                 11. License
  6. Database                    12. Container registry

  r. Return
EOF
        ask choice "Select a symptom:"
        case "$choice" in
            1) topic=failed-deploy ;; 2) topic=pending-pods ;;
            3) topic=restarting-pods ;; 4) topic=url ;; 5) topic=tls ;;
            6) topic=database ;; 7) topic=ssc ;; 8) topic=sast ;;
            9) topic=dast ;; 10) topic=dashboard ;; 11) topic=license ;;
            12) topic=registry ;; [Rr]) return ;;
            *) error "Invalid selection"; sleep 1; continue ;;
        esac
        echo
        operational_troubleshooting_topic "$topic"
        echo
        help_topic=$(help_failure_topic "$topic") || {
            error "No documentation mapping exists for troubleshooting topic: $topic"
            press_any
            continue
        }
        help_print_topic_reference "$help_topic"
        press_any
    done
}

operational_guidance_menu() {
    local choice output_dir bundle
    while true; do
        title "Operational guidance"
        cat <<'EOF'

  1. Environment overview
  2. Deployment plan
  3. Unfinished-work summary
  4. Troubleshooting assistant
  5. Networking, URLs, and TLS
  6. Secrets and license safety
  7. Lifecycle and data safety
  8. Versions and compatibility
  9. Backup and recovery guidance
 10. First-scan walkthrough
 11. Create sanitized diagnostics bundle

  r. Return
EOF
        ask choice "Select:"
        case "$choice" in
            1) wizard_environment_overview; press_any ;;
            2) wizard_deployment_plan; press_any ;;
            3) operational_unfinished_summary; press_any ;;
            4) operational_troubleshooting_menu ;;
            5) operational_print_urls; echo; operational_render_guide networking; press_any ;;
            6) operational_secret_help; echo; operational_render_guide secrets; press_any ;;
            7) operational_lifecycle_help; echo; operational_render_guide deployment; press_any ;;
            8) operational_version_overview; echo; operational_render_guide versions; press_any ;;
            9) operational_render_guide recovery; press_any ;;
            10) operational_render_guide first-scan; press_any ;;
            11)
                output_dir="${XDG_STATE_HOME:-$HOME/.local/state}/fortify-lab/diagnostics"
                if ! mkdir -p -- "$output_dir" || ! chmod 700 -- "$output_dir"; then
                    error "Could not create the private diagnostics output directory."
                    press_any
                    continue
                fi
                if bundle=$(operational_create_diagnostics_bundle "$output_dir"); then
                    note "Sanitized bundle created: $bundle"
                    note "Review it before sharing; no automated sanitizer can prove all context is safe."
                else
                    error "Diagnostics bundle creation failed."
                fi
                press_any
                ;;
            [Rr]) return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

install_jdk()      { command -v java   &>/dev/null && note "Already installed."  || sudo apt install -y openjdk-17-jre-headless; }
install_mkcert()   { command -v mkcert &>/dev/null && note "Already installed."  || sudo apt install -y mkcert; }
install_docker()   {
    if command -v docker &>/dev/null; then
        note "Already installed."
    else
        sudo apt install -y docker.io
    fi
    if ! [ -f "$HOME/.docker/config.json" ]; then
        note "Logging into Docker Hub (needed to pull Fortify images)..."
        docker login
    fi
}
install_microk8s() {
    if command -v microk8s &>/dev/null; then
        note "Already installed."
    else
        bash "$FORTIFY_HOME_K8S/scripts/install_microk8s.sh"
    fi
}


# ============================================================
# Deployment steps shared by Guided and Express modes
# ============================================================

GUIDED_STEP_ID=("prereqs" "inputs" "preflight" "certs" "dashboard" "secrets" "mysql" "postgresql" "ssc" "lim" "sast" "dast" "configure")
GUIDED_STEP_LABEL=("Host prerequisites" "Configuration and license" "Deployment pre-flight" "TLS certificates" "Kubernetes Dashboard" "Kubernetes Secrets" "MySQL" "PostgreSQL" "Software Security Center" "LIM" "ScanCentral SAST" "ScanCentral DAST" "Post-deploy configuration")
GUIDED_STEP_OPTIONAL=(1 0 0 0 0 0 0 0 0 0 0 0 1)
GUIDED_STEP_DURATION=("5-15 min" "2-5 min" "<1 min" "1-2 min" "2-5 min" "<1 min" "3-8 min" "3-8 min" "5-15 min" "3-8 min" "5-15 min" "5-15 min" "manual")
GUIDED_STEP_IMPACT=("host packages/add-ons" "local configuration" "read-only" "creates/updates lab TLS" "applies Dashboard" "creates/updates Secrets" "applies MySQL" "applies PostgreSQL" "applies SSC" "applies LIM" "applies SAST" "applies DAST" "manual configuration")
GUIDED_STEP_HELP=(
    "Install the host tools and MicroK8s add-ons used by the lab."
    "Review .env and provide a readable Fortify license before deployment."
    "Validate cluster readiness, storage, registry login, capacity, and required settings without changing the cluster."
    "Create the local CA and wildcard TLS material. Existing certificates are reused."
    "Deploy the default operational Web UI early so you can watch later workloads."
    "Create the Kubernetes credentials and application configuration. Secrets are never saved as wizard state."
    "Deploy MySQL and verify it accepts an authenticated query before SSC."
    "Deploy PostgreSQL and verify it accepts an authenticated query before DAST."
    "Deploy SSC only after the MySQL dependency gate passes."
    "Deploy LIM and wait for its application endpoint."
    "Deploy ScanCentral SAST only after SSC answers."
    "Deploy DAST Core and scanner after PostgreSQL, SSC, and LIM answer."
    "Configure DNS, the SSC ControllerToken, and the LIM pool when you are ready."
)

prereqs_complete() {
    local command
    for command in microk8s docker mkcert java keytool openssl envsubst curl; do
        command -v "$command" >/dev/null 2>&1 || return 1
    done
    return 0
}

inputs_complete() {
    [ -s "$ENV_FILE" ] || return 1
    ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
      fortify_resolve_license_file ) >/dev/null 2>&1
}

deployment_inputs_menu() {
    while true; do
        title "Configuration and license"
        printf '\n  .env:    %s\n' "$ENV_FILE"
        printf '  License: %s\n\n' "$(status_license)"
        echo "  1. Edit .env"
        echo "  2. Add or review the Fortify license"
        echo "  ?. Help for this step"
        echo "  r. Return to the guided step"
        echo
        ask choice "Select:"
        case "$choice" in
            1) edit_env ;;
            2) license_menu ;;
            \?) help_show_topic overview ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

preflight_inputs_complete() {
    local variable memory_gib disk_gib
    prereqs_complete && inputs_complete && cluster_reachable || return 1
    microk8s status >/dev/null 2>&1 || return 1
    $KUBECTL get storageclass nfs >/dev/null 2>&1 || return 1
    [ -s "$HOME/.docker/config.json" ] || return 1
    for variable in DOMAIN NAMESPACE DEFAULT_PASS FORTIFY_SSC_CHART_VERSION \
        FORTIFY_SSC_IMAGE_TAG FORTIFY_SCSAST_CHART_VERSION; do
        [ -n "${!variable:-}" ] || return 1
    done
    memory_gib=$(awk '/MemTotal:/ {print int($2/1024/1024)}' /proc/meminfo)
    disk_gib=$(df -Pk "$FORTIFY_HOME_K8S" | awk 'NR==2 {print int($4/1024/1024)}')
    [ "$memory_gib" -ge 16 ] && [ "$disk_gib" -ge 50 ]
}

resource_exists() {
    local namespace="$1" type="$2" name="$3"
    cluster_reachable && $KUBECTL -n "$namespace" get "$type" "$name" >/dev/null 2>&1
}

workload_ready() {
    local namespace="$1" type="$2" name="$3" desired ready
    cluster_reachable || return 1
    desired=$($KUBECTL -n "$namespace" get "$type" "$name" -o jsonpath='{.spec.replicas}' 2>/dev/null) || return 1
    ready=$($KUBECTL -n "$namespace" get "$type" "$name" -o jsonpath='{.status.readyReplicas}' 2>/dev/null) || return 1
    [ -n "$desired" ] && [ "${ready:-0}" -ge "$desired" ]
}

pod_prefix_ready() {
    local prefix="$1" pods total ready
    cluster_reachable || return 1
    pods=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
        | awk -v p="$prefix" '$1 ~ "^"p {print}')
    [ -n "$pods" ] || return 1
    total=$(wc -l <<<"$pods")
    ready=$(awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}' <<<"$pods")
    [ "$ready" -eq "$total" ]
}

dashboard_ready() {
    local dashboard_namespace
    dashboard_namespace=$(dashboard_access_namespace)
    if [ "$dashboard_namespace" = kubernetes-dashboard ]; then
        workload_ready "$dashboard_namespace" deployment kubernetes-dashboard-web &&
            workload_ready "$dashboard_namespace" deployment kubernetes-dashboard-kong &&
            resource_exists "$dashboard_namespace" ingress ingress-dashboard
    else
        workload_ready kube-system deployment kubernetes-dashboard &&
            resource_exists kube-system ingress ingress-dashboard
    fi
}

guided_step_complete() {
    case "$1" in
        prereqs) prereqs_complete ;;
        inputs) inputs_complete ;;
        preflight) preflight_inputs_complete ;;
        certs) [ -s "$FORTIFY_HOME_K8S/certs/tls.crt" ] && [ -s "$FORTIFY_HOME_K8S/certs/tls.key" ] ;;
        dashboard) dashboard_ready ;;
        secrets) resource_exists "$NAMESPACE" secret fortify-secrets ;;
        mysql) pod_prefix_ready mysql ;;
        postgresql) pod_prefix_ready postgresql ;;
        ssc) pod_prefix_ready ssc-webapp ;;
        lim) pod_prefix_ready lim ;;
        sast) pod_prefix_ready scancentral-sast ;;
        dast) pod_prefix_ready sdast ;;
        configure) return 1 ;; # Optional human tasks cannot be inferred safely.
        *) return 1 ;;
    esac
}

guided_step_status() {
    if guided_step_complete "$1"; then
        printf '%scomplete%s' "$GREEN" "$RESET"
    else
        printf '%spending%s' "$YELLOW" "$RESET"
    fi
}

wizard_deployment_plan() {
    local idx status
    operational_notice
    printf '\nDeployment plan (live-derived; preview only):\n'
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        if guided_step_complete "${GUIDED_STEP_ID[$idx]}"; then
            status=complete
        else
            status=pending
        fi
        printf '  %2d. %-30s %-8s %-10s %s\n' \
            "$((idx + 1))" "${GUIDED_STEP_LABEL[$idx]}" "$status" \
            "${GUIDED_STEP_DURATION[$idx]}" "${GUIDED_STEP_IMPACT[$idx]}"
    done
    printf '%s\n' 'No step above is destructive; persistent-data deletion is a separate expert action.'
}

wizard_environment_overview() {
    local id required_total=0 ready_total=0
    operational_environment_overview
    printf '\nDeployment indicators (application-level probes still decide usable health):\n'
    for id in inputs preflight dashboard secrets mysql postgresql ssc lim sast dast; do
        required_total=$((required_total + 1))
        if guided_step_complete "$id"; then
            ready_total=$((ready_total + 1))
            printf '  [ready indicator] %s\n' "$id"
        else
            printf '  [attention]       %s\n' "$id"
        fi
    done
    printf 'Overall deployment indicators: %d/%d ready; run authenticated dependency checks before scanning.\n' \
        "$ready_total" "$required_total"
}

# This is the sole operation dispatcher for both interactive deployment modes.
# Rendering guided status never calls it.
run_deployment_operation() {
    case "$1" in
        prereqs) prereqs_menu ;;
        inputs) deployment_inputs_menu ;;
        preflight) preflight_check ;;
        certs) bash "$FORTIFY_HOME_K8S/scripts/create-certs.sh" ;;
        dashboard) bash "$FORTIFY_HOME_K8S/apps/kubernetes-dashboard/deploy.sh" ;;
        secrets) bash "$FORTIFY_HOME_K8S/scripts/create-secrets.sh" ;;
        mysql) run_app_scripts "apps/mysql/start.sh" ;;
        postgresql) run_app_scripts "apps/postgresql/start.sh" ;;
        ssc) run_app_scripts "apps/ssc/start.sh" ;;
        lim) run_app_scripts "apps/lim/start.sh" ;;
        sast) run_app_scripts "apps/scsast/start.sh" ;;
        dast) run_app_scripts "apps/scdast/core/start.sh apps/scdast/scanner/start.sh" ;;
        configure) configure_menu ;;
        *) error "Unknown deployment operation: $1"; return 1 ;;
    esac
}

guided_deployment() {
    local idx="${1:-0}" choice id total="${#GUIDED_STEP_ID[@]}" result
    fortify_lab_require_acknowledgement || return 1
    while [ "$idx" -lt "$total" ]; do
        id="${GUIDED_STEP_ID[$idx]}"
        title "Guided deployment — Step $((idx + 1)) of $total"
        printf '\n  %s%s%s\n\n  %s\n' "$BOLD" "${GUIDED_STEP_LABEL[$idx]}" "$RESET" "${GUIDED_STEP_HELP[$idx]}"
        printf '\n  Current status: %s\n' "$(guided_step_status "$id")"
        [ "$id" = dashboard ] && printf '  Dashboard URL: https://dashboard.%s\n' "$DOMAIN"
        echo
        if guided_step_complete "$id"; then
            echo "  n. Next"
            echo "  r. Run again"
        else
            echo "  r. Run"
            echo "  t. Retry"
        fi
        [ "${GUIDED_STEP_OPTIONAL[$idx]}" -eq 1 ] && echo "  s. Skip optional step"
        [ "$idx" -gt 0 ] && echo "  b. Back"
        echo "  ?. Help for this step"
        echo "  q. Quit safely"
        echo
        ask choice "Select:"
        case "$choice" in
            [Nn])
                if guided_step_complete "$id"; then idx=$((idx + 1)); else error "Run this required step before continuing"; sleep 1; fi
                ;;
            [Rr]|[Tt])
                deploy_step "${GUIDED_STEP_LABEL[$idx]}" run_deployment_operation "$id"
                result=$?
                if [ "$result" -eq 0 ] && { [ "${GUIDED_STEP_OPTIONAL[$idx]}" -eq 1 ] || guided_step_complete "$id"; }; then
                    idx=$((idx + 1))
                else
                    error "The step is still incomplete. Correct the issue, then choose Retry."
                    help_print_topic_reference "$(help_guided_topic "$id")"
                    [ "$result" -eq 0 ] && press_any
                fi
                ;;
            [Ss])
                if [ "${GUIDED_STEP_OPTIONAL[$idx]}" -eq 1 ]; then
                    note "Skipped optional step; you can return to it later."
                    idx=$((idx + 1))
                else
                    error "${GUIDED_STEP_LABEL[$idx]} is required and cannot be skipped"
                    sleep 1
                fi
                ;;
            [Bb]) [ "$idx" -gt 0 ] && idx=$((idx - 1)) ;;
            \?) help_show_topic "$(help_guided_topic "$id")" ;;
            [Qq]) note "No wizard state or secrets were written. Live resources will be detected when you resume."; return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
    note "Guided deployment complete."
    press_any
}

resume_repair() {
    local idx id start=0 found=0 total="${#GUIDED_STEP_ID[@]}"
    fortify_lab_require_acknowledgement || return 1
    title "Resume or repair deployment"
    echo
    echo "  State is derived from current files and Kubernetes; no password or token is persisted."
    echo
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        id="${GUIDED_STEP_ID[$idx]}"
        printf '  %2d. %-30s %s\n' "$((idx + 1))" "${GUIDED_STEP_LABEL[$idx]}" "$(guided_step_status "$id")"
        if [ "$found" -eq 0 ] && [ "${GUIDED_STEP_OPTIONAL[$idx]}" -eq 0 ] && ! guided_step_complete "$id"; then
            start="$idx"
            found=1
        fi
    done
    echo
    note "Guided mode will start at the first incomplete required step; completed steps remain available for repair."
    press_any
    guided_deployment "$start"
}

deploy_from_scratch() {
    fortify_lab_require_acknowledgement || return 1
    title "Deploy lab from scratch"
    wizard_deployment_plan
    cat <<EOF

  This will run, in order:
    1. Pre-flight checks (license, prereqs, cluster reachable)
    2. scripts/create-certs.sh
    3. Kubernetes Dashboard (TLS ingress + readiness)
    4. scripts/create-secrets.sh
    5. apps/mysql/start.sh + apps/postgresql/start.sh   (wait until ready)
    6. apps/ssc/start.sh + apps/lim/start.sh            (wait until ready)
    7. apps/scsast/start.sh
    8. apps/scdast/core/start.sh + apps/scdast/scanner/start.sh

  The whole flow takes ~15-20 minutes. SSC's first start runs DB
  migrations; LIM does signing-cert setup. Watch logs in another
  terminal if you want progress.

EOF
    confirm "Proceed?" || return

    deploy_step "Pre-flight" run_deployment_operation preflight || return
    deploy_step "Certs" run_deployment_operation certs || return
    deploy_step "Dashboard" run_deployment_operation dashboard || return
    deploy_step "Secrets" run_deployment_operation secrets || return
    deploy_step "MySQL" run_deployment_operation mysql || return
    deploy_step "PostgreSQL" run_deployment_operation postgresql || return
    # shellcheck source=scripts/lib/dependency-health.sh
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    health_mysql_ready || return
    health_postgresql_ready || return
    deploy_step "SSC" run_deployment_operation ssc || return
    deploy_step "LIM" run_deployment_operation lim || return
    health_ssc_ready || return
    health_lim_ready || return
    deploy_step "SAST" run_deployment_operation sast || return
    deploy_step "DAST" run_deployment_operation dast || return
    note "Deploy complete. Use Advanced setup and configuration for DNS, the SSC token, and LIM."
    press_any
}

preflight_check() {
    local command releases memory_gib disk_gib variable
    for command in microk8s docker mkcert java keytool openssl envsubst curl; do
        command -v "$command" >/dev/null 2>&1 || {
            error "Missing prerequisite: $command (use option 3)"
            return 1
        }
    done
    source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh"
    fortify_resolve_license_file || return 1
    cluster_reachable || { error "Cluster not reachable"; return 1; }
    microk8s status --wait-ready >/dev/null 2>&1 || {
        error "MicroK8s is not ready"
        return 1
    }
    $KUBECTL get storageclass nfs >/dev/null 2>&1 || {
        error "Required NFS storage class is unavailable (use option 3)"
        return 1
    }
    releases=$($HELM -n "$NAMESPACE" list -q 2>/dev/null || true)
    if grep -Eq '^(mysql|postgresql|ssc|lim|scancentral-sast|sdast-core|sdast-scanner)$' <<<"$releases"; then
        error "Managed releases already exist; use Apps → Start / Upgrade instead"
        return 1
    fi
    [ -s "$HOME/.docker/config.json" ] || {
        error "Docker registry login is missing (use option 3)"
        return 1
    }
    for variable in DOMAIN NAMESPACE DEFAULT_PASS FORTIFY_SSC_CHART_VERSION \
        FORTIFY_SSC_IMAGE_TAG FORTIFY_SCSAST_CHART_VERSION; do
        [ -n "${!variable:-}" ] || {
            error "Required .env setting is empty: $variable"
            return 1
        }
    done
    memory_gib=$(awk '/MemTotal:/ {print int($2/1024/1024)}' /proc/meminfo)
    disk_gib=$(df -Pk "$FORTIFY_HOME_K8S" | awk 'NR==2 {print int($4/1024/1024)}')
    [ "$memory_gib" -ge 16 ] || {
        error "At least 16 GiB host memory is required"
        return 1
    }
    [ "$disk_gib" -ge 50 ] || {
        error "At least 50 GiB free disk is required for a fresh deployment"
        return 1
    }
    return 0
}

deploy_step() {
    local label="$1"; shift
    section "$label"
    if "$@"; then
        note "$label OK"
    else
        error "$label failed — aborting deploy"
        press_any
        return 1
    fi
}

wait_pod() {
    local prefix="$1" timeout="${2:-300}"
    note "Waiting up to ${timeout}s for $prefix pod to be Ready..."
    local pod
    local started=$SECONDS remaining
    while [ $((SECONDS - started)) -lt "$timeout" ]; do
        pod=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
              | awk -v p="$prefix" '$1 ~ "^"p {print $1; exit}')
        [ -n "$pod" ] && break
        sleep 2
    done
    [ -n "$pod" ] || { error "No pod matching '$prefix' appeared"; return 1; }
    remaining=$((timeout - (SECONDS - started)))
    [ "$remaining" -gt 0 ] || remaining=1
    $KUBECTL -n "$NAMESPACE" wait --for=condition=Ready \
        --timeout="${remaining}s" "pod/$pod" || {
        error "$pod did not become Ready"
        return 1
    }
}


# ============================================================
# Main menu
# ============================================================

main_menu() {
    while true; do
        title "Fortify Lab"
        fortify_lab_menu_banner
        section "Status"
        printf '  %s\n' "$(status_prereqs)"
        printf '  %s\n' "$(status_license)"
        printf '  %s\n' "$(status_cluster)"
        status_user

        section "Deploy"
        echo "   1. Guided deployment (recommended)"
        echo "   2. Express deployment"
        echo "   3. Resume or repair deployment"
        echo "   4. Manage individual components (expert)"
        echo "   5. Kubernetes Dashboard access"

        section "Diagnostics and advanced"
        echo "   6. Diagnostics / live status"
        echo "   7. Advanced setup and configuration"

        section "Operations"
        echo "   8. Stream logs (all pods)"
        echo "   9. Cluster snapshot"
        echo "  10. Tail one pod"
        echo "  11. URLs & credentials"
        echo "  12. Image versions"
        echo "  13. Edit .env"

        section "Learn"
        echo "  14. Help Center / Fortify Knowledge Center"
        echo "  15. Operational guidance and troubleshooting"

        echo
        echo "   q. Quit"
        echo
        ask choice "Select:"

        case "$choice" in
            1)  guided_deployment ;;
            2)  deploy_from_scratch ;;
            3)  resume_repair ;;
            4)  apps_menu ;;
            5)  dashboard_access_menu ;;
            6)  live_status ;;
            7)  advanced_menu ;;
            8)  stream_logs ;;
            9)  cluster_status ;;
           10)  logs_menu ;;
           11)  urls_creds ;;
           12)  versions_menu ;;
           13)  edit_env ;;
           14)  help_center ;;
           15)  operational_guidance_menu ;;
            [Qq]) clear; exit 0 ;;
            *)   error "Invalid choice"; sleep 1 ;;
        esac
    done
}


# ============================================================
# Entry
# ============================================================

usage() {
    cat <<EOF
Fortify Lab management wizard.

Usage:
  ./start_wizard.sh                  Launch the interactive menu.
  ./start_wizard.sh --accept-lab-use Explicitly acknowledge lab-only use for automation.
  ./start_wizard.sh -h | --help      Show this message.

Environment overrides:
  FORTIFY_HOME_K8S    Repo root (defaults to the script's directory).
  EDITOR              Editor used by 'Edit .env' (defaults to nano).
  NO_COLOR            Disable color output if set to any value.
  WIZARD_NOMAIN       Set to 1 to source this file without entering the menu
                      (for tests / scripting).

Run as your normal user — the wizard sudo's only the commands that genuinely
need root (apt, snap). Avoid 'sudo ./start_wizard.sh': it would create an
mkcert CA owned by root and rotate every cert the lab has issued.
EOF
}

# Allow sourcing the file for testing without entering the main menu.
if [ -z "${WIZARD_NOMAIN:-}" ]; then
    case "${1:-}" in
        -h|--help) usage; exit 0 ;;
        ''|--accept-lab-use) ;;
        *) error "Unsupported argument: ${1}"; usage >&2; exit 2 ;;
    esac
    if [ "$#" -gt 1 ]; then
        error "Only one command-line option is supported."
        usage >&2
        exit 2
    fi
    fortify_lab_detect_accept_flag "$@"
    fortify_lab_require_acknowledgement || exit 1
    bootstrap_env
    main_menu
fi
