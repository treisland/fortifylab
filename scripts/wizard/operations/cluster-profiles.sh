# shellcheck shell=bash
# Module: operations/cluster-profiles
# Responsibility: Cluster profile selection, context confirmation, readiness, diagnostics, and menu flow.
# Requires: environment helpers, UI helpers, kubectl
# Exports: cluster_profile_*
# Side effects: Reads local and remote Kubernetes contexts; menu selection may update the active profile.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_CLUSTER_PROFILES_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_CLUSTER_PROFILES_LOADED=1

# Advanced coordinated cluster profiles (read-only remote checks)
# ============================================================

cluster_profile_selected() {
    printf '%s\n' "${FORTIFY_CLUSTER_PROFILE:-local}"
}

cluster_profile_ids() {
    local names="${FORTIFY_CLUSTER_PROFILE_NAMES:-local}"
    printf '%s\n' $names
}

cluster_profile_env_prefix() {
    local id="$1"
    printf '%s\n' "$id" | tr '[:lower:]-.' '[:upper:]__' | tr -cd 'A-Z0-9_'
}

cluster_profile_field() {
    local id="$1" field="$2" default="${3:-}" prefix var value
    prefix=$(cluster_profile_env_prefix "$id")
    var="FORTIFY_CLUSTER_PROFILE_${prefix}_${field}"
    value="${!var:-}"
    [ -n "$value" ] || value="$default"
    printf '%s\n' "$value"
}

cluster_profile_current_context() {
    [ -n "${KUBECTL:-}" ] || return 1
    $KUBECTL config current-context 2>/dev/null
}

cluster_profile_report() {
    local id="${1:-$(cluster_profile_selected)}" current configured role ssh_host components storage ingress
    current=$(cluster_profile_current_context || true)
    configured=$(cluster_profile_field "$id" KUBE_CONTEXT "")
    role=$(cluster_profile_field "$id" ROLE "single-node")
    ssh_host=$(cluster_profile_field "$id" SSH_HOST "")
    components=$(cluster_profile_field "$id" ENABLED_COMPONENTS "")
    storage=$(cluster_profile_field "$id" STORAGE_CLASS "nfs")
    ingress=$(cluster_profile_field "$id" INGRESS_MODE "microk8s-traefik")
    printf 'Selected cluster profile: %s\n' "$id"
    printf '  Role:               %s\n' "$role"
    printf '  Kube context:       %s\n' "${configured:-<current context>}"
    printf '  Current context:    %s\n' "${current:-<unavailable>}"
    printf '  SSH host:           %s\n' "${ssh_host:-<local>}"
    printf '  Enabled components: %s\n' "${components:-<deployment profile decides>}"
    printf '  Storage class:      %s\n' "$storage"
    printf '  Ingress mode:       %s\n' "$ingress"
    if [ -n "$configured" ] && [ -n "$current" ] && [ "$configured" != "$current" ]; then
        printf '  Warning: configured context does not match the active kubectl context.\n'
    fi
}

cluster_profile_confirm_target_context() {
    local id="${1:-$(cluster_profile_selected)}" configured current
    configured=$(cluster_profile_field "$id" KUBE_CONTEXT "")
    [ -n "$configured" ] || return 0
    current=$(cluster_profile_current_context || true)
    if [ "$current" = "$configured" ]; then
        return 0
    fi
    error "Selected cluster profile '$id' expects kube context '$configured', but current context is '${current:-unavailable}'."
    printf '%s\n' 'Switch kubectl/microk8s to the expected context or choose the local profile before deploying.' >&2
    wizard_log_event "action=cluster_profile_context state=blocked profile=$id expected=$configured current=${current:-unavailable}"
    return 1
}

cluster_profile_remote_readiness() {
    local id="${1:-$(cluster_profile_selected)}" ssh_host role kube_context storage ingress
    ssh_host=$(cluster_profile_field "$id" SSH_HOST "")
    role=$(cluster_profile_field "$id" ROLE "single-node")
    kube_context=$(cluster_profile_field "$id" KUBE_CONTEXT "")
    storage=$(cluster_profile_field "$id" STORAGE_CLASS "nfs")
    ingress=$(cluster_profile_field "$id" INGRESS_MODE "microk8s-traefik")
    section "Remote host readiness"
    printf 'Profile:       %s\n' "$id"
    printf 'Role:          %s\n' "$role"
    printf 'Kube context:  %s\n' "${kube_context:-<current context>}"
    printf 'Storage class: %s\n' "$storage"
    printf 'Ingress mode:  %s\n' "$ingress"
    if [ -z "$ssh_host" ]; then
        note "No SSH host is configured for this profile; treating it as the local single-machine path."
        return 0
    fi
    printf 'SSH host:      %s\n\n' "$ssh_host"
    ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_host" 'sh -c '\''
        printf "Host: %s\n" "$(hostname 2>/dev/null || printf unknown)"
        if [ -r /etc/os-release ]; then . /etc/os-release; printf "OS: %s\n" "${PRETTY_NAME:-unknown}"; else printf "OS: unknown\n"; fi
        for cmd in docker microk8s kubectl helm snap; do
            if command -v "$cmd" >/dev/null 2>&1; then printf "OK: %s\n" "$cmd"; else printf "MISSING: %s\n" "$cmd"; fi
        done
        if command -v microk8s >/dev/null 2>&1; then
            microk8s status --wait-ready --timeout 5 >/dev/null 2>&1 && printf "OK: microk8s-ready\n" || printf "WARN: microk8s-not-ready\n"
        fi
    '\''' || {
        error "Unable to complete read-only SSH readiness check for $ssh_host."
        return 1
    }
}

cluster_profile_diagnostics() {
    title "Cluster profile diagnostics"
    echo
    cluster_profile_report
    echo
    if cluster_profile_confirm_target_context "$(cluster_profile_selected)"; then
        note "Cluster profile context is safe for deployment operations."
    else
        note "Deployment operations are blocked until the selected context matches."
    fi
    echo
    cluster_profile_remote_readiness "$(cluster_profile_selected)"
}

cluster_profile_menu() {
    local choice id ids=() idx
    while true; do
        mapfile -t ids < <(cluster_profile_ids)
        title "Cluster profiles"
        echo
        cluster_profile_report
        cat <<'EOF'

Select a named target profile for advanced diagnostics and deployment safety.
The default local profile preserves the single-machine path. Remote SSH checks
are read-only and never copy secrets or mutate remote hosts.

EOF
        idx=1
        for id in "${ids[@]}"; do
            printf '  %d. %s\n' "$idx" "$id"
            idx=$((idx + 1))
        done
        cat <<'EOF'

  d. Readiness diagnostics for selected profile
  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            [Dd]) cluster_profile_diagnostics; press_any ;;
            [Rr]) return ;;
            ''|*[!0-9]*) error "Invalid selection"; sleep 1 ;;
            *)
                if [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -le "${#ids[@]}" ]; then
                    id="${ids[$((choice - 1))]}"
                    if confirm "Save cluster profile '$id' to .env?"; then
                        env_apply_updates cluster-profile "FORTIFY_CLUSTER_PROFILE=$id"
                    else
                        FORTIFY_CLUSTER_PROFILE="$id"
                        note "Using cluster profile '$id' for this wizard session only."
                    fi
                else
                    error "Invalid selection"
                    sleep 1
                fi
                ;;
        esac
    done
}

# ============================================================
# Per-app helpers
