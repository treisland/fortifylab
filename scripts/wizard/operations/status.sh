# shellcheck shell=bash
# Module: operations/status
# Responsibility: Read-only prerequisite, license, cluster, and user status probes.
# Requires: bootstrap globals, UI helpers, kubectl adapter variables
# Exports: cluster_reachable, status_prereqs, status_license, status_cluster, status_user
# Side effects: Reads host and Kubernetes status; does not mutate resources.
# Interactive: no.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_STATUS_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_STATUS_LOADED=1

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
    command -v openssl  &>/dev/null || missing+=("openssl")
    command -v curl     &>/dev/null || missing+=("curl")
    command -v envsubst &>/dev/null || missing+=("envsubst")
    command -v sg       &>/dev/null || command -v newgrp &>/dev/null || missing+=("sg/newgrp")
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
    local pods total ready prefixes selected_total selected_ready
    pods=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null || true)
    total=$(printf '%s\n' "$pods" | awk 'NF {c++} END{print c+0}')
    if [ "$total" -eq 0 ]; then
        printf '%s Cluster up, no pods deployed yet\n' "$WARN_MARK"
        return
    fi
    prefixes=$(lab_lifecycle_selected_pod_prefixes)
    if [ -n "$prefixes" ]; then
        read -r selected_ready selected_total <<EOF
$(printf '%s\n' "$pods" | awk -v prefixes="$prefixes" '
BEGIN { prefix_count=split(prefixes,p," ") }
NF {
    matched=0
    for (idx=1; idx<=prefix_count; idx++) {
        if (p[idx] != "" && index($1,p[idx]) == 1) { matched=1; break }
    }
    if (matched) {
        total++
        if ($3 == "Running") {
            n=split($2,a,"/")
            if (a[1] == a[2]) ready++
        }
    }
}
END { print ready+0, total+0 }')
EOF
        if [ "$selected_total" -eq 0 ]; then
            printf '%s Cluster: selected profile has no pods deployed yet\n' "$WARN_MARK"
        elif [ "$selected_ready" -eq "$selected_total" ]; then
            printf '%s Cluster: selected profile pods ready (%d/%d running)\n' "$OK_MARK" "$selected_ready" "$selected_total"
        else
            printf '%s Cluster: selected profile pods ready (%d/%d running)\n' "$WARN_MARK" "$selected_ready" "$selected_total"
        fi
        return
    fi
    ready=$(printf '%s\n' "$pods" | awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}')
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
