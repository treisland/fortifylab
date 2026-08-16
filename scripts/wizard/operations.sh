#!/usr/bin/env bash
# shellcheck shell=bash

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

lab_lifecycle_current_profile() {
    guided_apply_deployment_profile "${GUIDED_DEPLOYMENT_PROFILE:-${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}}"
}

lab_lifecycle_step_is_workload() {
    case "$1" in
        mysql|postgresql|ssc|lim|sast_controller|sast_sensor|dast_core|dast_scanner|sample_juice_shop|sample_webgoat|sample_dvwa) return 0 ;;
        *) return 1 ;;
    esac
}

lab_lifecycle_app_index_selected() {
    local idx="$1" step="${APP_GUIDED_STEP[$idx]:-}"
    case "$step" in
        mysql|postgresql|ssc|lim) guided_component_selected "$step" ;;
        sast) guided_component_selected sast_controller || guided_component_selected sast_sensor ;;
        dast) guided_component_selected dast_core || guided_component_selected dast_scanner ;;
        sample_juice_shop|sample_webgoat|sample_dvwa) guided_component_selected "$step" ;;
        *) return 1 ;;
    esac
}

lab_lifecycle_selected_pod_prefixes() {
    local idx prefix prefixes=""
    lab_lifecycle_current_profile >/dev/null 2>&1 || true
    for idx in "${!APP_PODS[@]}"; do
        lab_lifecycle_app_index_selected "$idx" || continue
        prefix="${APP_PODS[$idx]}"
        case " $prefixes " in
            *" $prefix "*) ;;
            *) prefixes="${prefixes:+$prefixes }$prefix" ;;
        esac
    done
    printf '%s\n' "$prefixes"
}

lab_lifecycle_selected_step_indexes() {
    local idx id
    lab_lifecycle_current_profile >/dev/null 2>&1 || true
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        id="${GUIDED_STEP_ID[$idx]}"
        lab_lifecycle_step_is_workload "$id" && printf '%s\n' "$idx"
    done
}

lab_lifecycle_step_stop_destroy_script() {
    local operation="$1" step="$2"
    case "$operation:$step" in
        stop:mysql) printf '%s\n' "apps/mysql/stop.sh" ;;
        stop:postgresql) printf '%s\n' "apps/postgresql/stop.sh" ;;
        stop:ssc) printf '%s\n' "apps/ssc/stop.sh" ;;
        stop:lim) printf '%s\n' "apps/lim/stop.sh" ;;
        stop:sast_controller|stop:sast_sensor) printf '%s\n' "apps/scsast/stop.sh" ;;
        stop:dast_core) printf '%s\n' "apps/scdast/core/stop.sh" ;;
        stop:dast_scanner) printf '%s\n' "apps/scdast/scanner/stop.sh" ;;
        destroy:mysql) printf '%s\n' "apps/mysql/destroy.sh" ;;
        destroy:postgresql) printf '%s\n' "apps/postgresql/destroy.sh" ;;
        destroy:ssc) printf '%s\n' "apps/ssc/destroy.sh" ;;
        destroy:lim) printf '%s\n' "apps/lim/destroy.sh" ;;
        destroy:sast_controller|destroy:sast_sensor) printf '%s\n' "apps/scsast/destroy.sh" ;;
        destroy:dast_core) printf '%s\n' "apps/scdast/core/destroy.sh" ;;
        destroy:dast_scanner) printf '%s\n' "apps/scdast/scanner/destroy.sh" ;;
        *) return 1 ;;
    esac
}

lab_lifecycle_script_list() {
    local operation="$1" scope="${2:-selected}" idx field script seen="" step
    if [ "$scope" = "all" ]; then
        for ((idx=${#APP_LABEL[@]} - 1; idx >= 0; idx--)); do
            app_index_in_full_lifecycle "$idx" || continue
            case "$operation" in
                destroy) field="${APP_DESTROY[$idx]}" ;;
                stop) field="${APP_STOP[$idx]}" ;;
                *) return 1 ;;
            esac
            for script in $field; do
                printf '  - %-20s %s\n' "${APP_LABEL[$idx]}" "$script"
            done
        done
        return 0
    fi
    mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
    for ((idx=${#_lab_lifecycle_indexes[@]} - 1; idx >= 0; idx--)); do
        step="${GUIDED_STEP_ID[${_lab_lifecycle_indexes[$idx]}]}"
        script=$(lab_lifecycle_step_stop_destroy_script "$operation" "$step") || continue
        case " $seen " in
            *" $script "*) continue ;;
        esac
        seen="${seen:+$seen }$script"
        printf '  - %-20s %s\n' "${GUIDED_STEP_LABEL[${_lab_lifecycle_indexes[$idx]}]}" "$script"
    done
}

lab_shutdown_deployments() {
    local scope="${1:-selected}" idx rc=0 script step seen=""
    section "Shutdown lab deployments"
    if [ "$scope" = "all" ]; then
        note "Stopping all lab workloads in dependency-safe order. Persistent data is preserved."
        wizard_log_event "action=lab_lifecycle_start operation=shutdown scope=all mode=non_destructive"
        for ((idx=${#APP_LABEL[@]} - 1; idx >= 0; idx--)); do
            app_index_in_full_lifecycle "$idx" || continue
            note "Stopping ${APP_LABEL[$idx]}..."
            wizard_log_event "action=lab_lifecycle_component operation=shutdown scope=all component=${APP_GUIDED_STEP[$idx]}"
            run_app_scripts "${APP_STOP[$idx]}"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=shutdown scope=all state=failed component=${APP_GUIDED_STEP[$idx]} exit_code=$rc"
                return "$rc"
            fi
        done
    else
        lab_lifecycle_current_profile
        note "Stopping selected profile workloads: $GUIDED_DEPLOYMENT_PROFILE_LABEL. Persistent data is preserved."
        wizard_log_event "action=lab_lifecycle_start operation=shutdown scope=selected profile=$GUIDED_DEPLOYMENT_PROFILE mode=non_destructive"
        mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
        for ((idx=${#_lab_lifecycle_indexes[@]} - 1; idx >= 0; idx--)); do
            step="${GUIDED_STEP_ID[${_lab_lifecycle_indexes[$idx]}]}"
            script=$(lab_lifecycle_step_stop_destroy_script stop "$step") || continue
            case " $seen " in
                *" $script "*) continue ;;
            esac
            seen="${seen:+$seen }$script"
            note "Stopping ${GUIDED_STEP_LABEL[${_lab_lifecycle_indexes[$idx]}]}..."
            wizard_log_event "action=lab_lifecycle_component operation=shutdown scope=selected component=$step"
            run_app_scripts "$script"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=shutdown scope=selected state=failed component=$step exit_code=$rc"
                return "$rc"
            fi
        done
    fi
    wizard_log_event "action=lab_lifecycle_finish operation=shutdown scope=$scope state=complete"
    note "Lab workloads stopped. Data volumes and configuration remain in place."
}

lab_start_deployments() {
    local scope="${1:-selected}" idx rc=0 previous_mode="${GUIDED_MODE_CONTEXT:-}" step label
    section "Start lab deployments"
    if [ "$scope" = "all" ]; then
        note "Starting all lab workloads in dependency order and verifying readiness after each component."
        wizard_log_event "action=lab_lifecycle_start operation=start scope=all mode=non_destructive"
        GUIDED_MODE_CONTEXT=lifecycle
        for idx in "${!APP_LABEL[@]}"; do
            app_index_in_full_lifecycle "$idx" || continue
            guided_run_and_verify "${APP_GUIDED_STEP[$idx]}" "${APP_LABEL[$idx]}"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                GUIDED_MODE_CONTEXT="$previous_mode"
                wizard_log_event "action=lab_lifecycle_finish operation=start scope=all state=failed component=${APP_GUIDED_STEP[$idx]} exit_code=$rc"
                return "$rc"
            fi
        done
    else
        lab_lifecycle_current_profile
        note "Starting selected profile workloads: $GUIDED_DEPLOYMENT_PROFILE_LABEL."
        wizard_log_event "action=lab_lifecycle_start operation=start scope=selected profile=$GUIDED_DEPLOYMENT_PROFILE mode=non_destructive"
        GUIDED_MODE_CONTEXT=lifecycle
        mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
        for idx in "${_lab_lifecycle_indexes[@]}"; do
            step="${GUIDED_STEP_ID[$idx]}"
            label="${GUIDED_STEP_LABEL[$idx]}"
            guided_run_and_verify "$step" "$label"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                GUIDED_MODE_CONTEXT="$previous_mode"
                wizard_log_event "action=lab_lifecycle_finish operation=start scope=selected state=failed component=$step exit_code=$rc"
                return "$rc"
            fi
        done
    fi
    GUIDED_MODE_CONTEXT="$previous_mode"
    wizard_log_event "action=lab_lifecycle_finish operation=start scope=$scope state=complete"
    note "Lab workloads are started and verified."
}

lab_teardown_preview() {
    local scope="${1:-selected}"
    if [ "$scope" = "all" ]; then
        section "Full lab teardown preview"
        cat <<EOF
This destructive operation runs every component destroy script below in
dependency-safe order. It deletes application deployments and their data so
the lab can be started again from a clean slate.

EOF
    else
        lab_lifecycle_current_profile
        section "Selected profile teardown preview"
        cat <<EOF
This destructive operation runs destroy scripts only for the selected profile:
$GUIDED_DEPLOYMENT_PROFILE_LABEL. Dependencies are included only when the
profile requires them, and unrelated lab workloads are left alone.

EOF
    fi
    lab_lifecycle_script_list destroy "$scope"
}

lab_destroy_deployments() {
    local scope="${1:-selected}" idx rc=0 confirmation expected script step seen=""
    if [ "$scope" = "all" ]; then
        expected="DESTROY FORTIFY LAB"
    else
        expected="DESTROY SELECTED PROFILE"
    fi
    fortify_lab_show_action_warning destructive
    lab_teardown_preview "$scope"
    printf '\nType %s to continue: ' "$expected"
    IFS= read -r confirmation
    if [ "$confirmation" != "$expected" ]; then
        note "Teardown cancelled."
        wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=$scope state=cancelled"
        return 1
    fi
    wizard_log_event "action=lab_lifecycle_start operation=destroy scope=$scope mode=destructive"
    if [ "$scope" = "all" ]; then
        for ((idx=${#APP_LABEL[@]} - 1; idx >= 0; idx--)); do
            app_index_in_full_lifecycle "$idx" || continue
            note "Destroying ${APP_LABEL[$idx]}..."
            wizard_log_event "action=lab_lifecycle_component operation=destroy scope=all component=${APP_GUIDED_STEP[$idx]}"
            run_app_scripts "${APP_DESTROY[$idx]}"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=all state=failed component=${APP_GUIDED_STEP[$idx]} exit_code=$rc"
                return "$rc"
            fi
        done
    else
        mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
        for ((idx=${#_lab_lifecycle_indexes[@]} - 1; idx >= 0; idx--)); do
            step="${GUIDED_STEP_ID[${_lab_lifecycle_indexes[$idx]}]}"
            script=$(lab_lifecycle_step_stop_destroy_script destroy "$step") || continue
            case " $seen " in
                *" $script "*) continue ;;
            esac
            seen="${seen:+$seen }$script"
            note "Destroying ${GUIDED_STEP_LABEL[${_lab_lifecycle_indexes[$idx]}]}..."
            wizard_log_event "action=lab_lifecycle_component operation=destroy scope=selected component=$step"
            run_app_scripts "$script"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=selected state=failed component=$step exit_code=$rc"
                return "$rc"
            fi
        done
    fi
    wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=$scope state=complete"
    note "Lab deployments and data have been destroyed for the requested scope."
}

lab_lifecycle_menu() {
    local choice
    while true; do
        lab_lifecycle_current_profile
        title "Lab lifecycle controls"
        cat <<EOF

  Active profile: $GUIDED_DEPLOYMENT_PROFILE_LABEL

  1. Shutdown selected profile workloads (preserve data)
  2. Start selected profile workloads
  3. Destroy selected profile deployments and data

  4. Shutdown all lab deployments (preserve data)
  5. Start all lab deployments
  6. Destroy all lab deployments and data
  7. Complete lab reset wizard

  r. Return
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1)
                confirm "Stop selected profile workloads while preserving data?" || continue
                lab_shutdown_deployments selected
                press_any ;;
            2)
                lab_start_deployments selected
                press_any ;;
            3)
                lab_destroy_deployments selected
                press_any ;;
            4)
                confirm "Stop all lab workloads while preserving data?" || continue
                lab_shutdown_deployments all
                press_any ;;
            5)
                lab_start_deployments all
                press_any ;;
            6)
                lab_destroy_deployments all
                press_any ;;
            7)
                lab_reset_menu ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


# ============================================================
# Apps submenu
# ============================================================

apps_menu() {
    apps_menu_for_scope "all"
}

sample_apps_menu() {
    fortify_lab_show_action_warning vulnerable-sample
    apps_menu_for_scope "samples"
}

apps_menu_for_scope() {
    local scope="${1:-all}" heading="Apps"
    [ "$scope" = "samples" ] && heading="Sample applications"
    while true; do
        title "$heading"
        if [ "$scope" = "samples" ]; then
            printf '\n  Intentionally vulnerable lab targets for SAST and DAST practice.\n'
            printf '  Keep these applications isolated to your lab network.\n'
        fi
        printf '\n  %-3s %-20s %s\n' "#" "Name" "Status"
        printf '  %s\n' "─────────────────────────────────────"
        local i display_idx visible=0 visible_indices=()
        for i in "${!APP_LABEL[@]}"; do
            if [ "$scope" = "samples" ]; then
                app_index_is_sample "$i" || continue
            fi
            visible=$((visible + 1))
            display_idx="$visible"
            [ "$scope" = "all" ] && display_idx=$((i + 1))
            visible_indices[$visible]="$i"
            printf '  %-3d %-20s %s\n' \
                "$display_idx" "${APP_LABEL[$i]}" "$(app_status "${APP_PODS[$i]}")"
        done
        [ "$visible" -eq 0 ] && printf '  %s\n' "No sample applications are registered."
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
                if [ "$choice" -ge 1 ]; then
                    if [ "$scope" = "samples" ]; then
                        if [ "$choice" -le "$visible" ] && [ -n "${visible_indices[$choice]:-}" ]; then
                            app_action_menu "${visible_indices[$choice]}"
                        else
                            error "Select one of the sample application numbers shown above."
                            sleep 1
                        fi
                    elif [ "$choice" -le "${#APP_LABEL[@]}" ]; then
                        app_action_menu $((choice - 1))
                    else
                        error "Out of range"
                        sleep 1
                    fi
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
        url=$(app_url_display_for_index "$idx")

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
                if app_start_config_guard "$idx"; then
                    run_app_scripts "${APP_START[$idx]}"
                fi
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
    url=$(app_url_display_for_index "$idx")
    section "${APP_LABEL[$idx]}"
    [ -n "$url" ] && printf '  URL: %s\n' "$url"
    case "${APP_LABEL[$idx]}" in
        SSC)
            echo "  Login username: admin"
            echo "  Password: refer to the SSC documentation for the default password."
            ;;
        LIM)
            echo "  Login username: lim_admin"
            echo "  Password: stored in Kubernetes Secret lim-admin-credentials"
            ;;
        "ScanCentral SAST")
            echo "  Controller URL: $url"
            echo "  Tokens: use URLs & credentials to reveal or retrieve commands."
            ;;
        "ScanCentral DAST")
            echo "  API URL: ${SCDAST_API_URL:-<unset>}"
            echo "  Credentials: use URLs & credentials to reveal or retrieve commands."
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
    local ip expected_hosts
    ip=$(fortify_lab_node_ip)
    expected_hosts=$(fortify_lab_hostnames_inline)
    cat <<EOF

  -- Client side ------------------------------------------------
  Add to your client's /etc/hosts (or Pi-hole DNS):

    $ip   $expected_hosts

  Use the MicroK8s lab node IP shown above. If the names point at a Proxmox,
  Traefik, or other reverse-proxy endpoint without matching routes, browsers
  commonly show TRAEFIK DEFAULT CERT and then a plain 404 page.

  -- In-cluster side --------------------------------------------
  Pods inside the cluster need to resolve $DOMAIN themselves
  (e.g. ScanCentral SAST workers call https://sast.$DOMAIN/scancentral-ctrl).
  We patch CoreDNS's hosts plugin so they resolve to this node's IP.

EOF
    if confirm "Apply CoreDNS hosts override now?"; then
        fortify_ensure_coredns_lab_hosts || return 1
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
    2. Sign in as lim_admin. Retrieve the lab-generated password from
       URLs & credentials if you need to recover it.
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
        --type=merge -p "{"data":{"truststore":"$(base64 -w0 < "$TRUSTSTORE")"}}"
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

k8s_resource_names() {
    local kind="$1" filter="${2:-}" prefix="${3:-}" name
    [ -n "$KUBECTL" ] || return 1
    while IFS= read -r name; do
        name="${name#*/}"
        [ -n "$name" ] || continue
        [ -z "$prefix" ] || [[ "$name" == "$prefix"* ]] || continue
        [ -z "$filter" ] || [[ "$name" == *"$filter"* ]] || continue
        printf '%s\n' "$name"
    done < <($KUBECTL -n "$NAMESPACE" get "$kind" -o name 2>/dev/null)
}

k8s_select_resource() {
    local kind="$1" prompt="${2:-Select resource}" filter="${3:-}" prefix="${4:-}"
    local resources=() i sel exact
    K8S_SELECTED_RESOURCE_KIND=""
    K8S_SELECTED_RESOURCE_NAME=""

    while true; do
        mapfile -t resources < <(k8s_resource_names "$kind" "$filter" "$prefix")
        printf '\n%s\n' "$prompt"
        if [ -n "$filter" ]; then
            printf '  Filter: %s\n' "$filter"
        fi
        if [ -n "$prefix" ]; then
            printf '  Scope:  %s*\n' "$prefix"
        fi
        if [ ${#resources[@]} -eq 0 ]; then
            note "No ${kind}s matched '${filter:-all}'."
        else
            for i in "${!resources[@]}"; do
                printf '  %2d. %s\n' $((i + 1)) "${resources[$i]}"
            done
        fi
        printf '\n  f. Filter list   x. Enter exact name   b. Back\n'
        ask sel "${kind^} number:"
        case "$sel" in
            [Bb]|"") return 1 ;;
            [Ff])
                ask filter "Filter (substring, blank=all):"
                ;;
            [Xx])
                ask exact "Exact ${kind} name:"
                [ -n "$exact" ] || { error "Name cannot be blank"; continue; }
                K8S_SELECTED_RESOURCE_KIND="$kind"
                K8S_SELECTED_RESOURCE_NAME="$exact"
                return 0
                ;;
            *)
                if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -le ${#resources[@]} ]; then
                    K8S_SELECTED_RESOURCE_KIND="$kind"
                    K8S_SELECTED_RESOURCE_NAME="${resources[$((sel-1))]}"
                    return 0
                fi
                error "Invalid selection."
                ;;
        esac
    done
}

pod_has_restarts() {
    local pod="$1"
    $KUBECTL -n "$NAMESPACE" get pod "$pod" \
        -o jsonpath='{range .status.containerStatuses[*]}{.restartCount}{"\\n"}{end}' 2>/dev/null \
        | awk '$1 > 0 { found=1 } END { exit found ? 0 : 1 }'
}

restore_int_trap() {
    local saved_trap="${1:-}"
    if [ -n "$saved_trap" ]; then
        eval "$saved_trap"
    else
        trap - INT
    fi
}

follow_pod_logs_safe() {
    local pod="$1" tail_lines="${2:-100}" pid rc saved_int_trap interrupted=0
    saved_int_trap=$(trap -p INT || true)
    (
        trap - INT
        $KUBECTL -n "$NAMESPACE" logs --all-containers --follow --tail="$tail_lines" --ignore-errors=true "$pod"
    ) &
    pid=$!
    trap 'interrupted=1; kill -INT "$pid" 2>/dev/null; sleep 0.2; kill -TERM "$pid" 2>/dev/null' INT
    wait "$pid"
    rc=$?
    restore_int_trap "$saved_int_trap"
    if [ "$interrupted" -eq 1 ] || [ "$rc" -ge 130 ]; then
        note "Stopped following logs for $pod."
        return 0
    fi
    return "$rc"
}

pod_log_action_menu() {
    local pod="$1" choice previous_label
    while true; do
        previous_label="Previous container logs"
        pod_has_restarts "$pod" || previous_label="Previous container logs (if available)"
        printf '\nPod: %s\n' "$pod"
        printf '  1. Recent logs\n'
        printf '  2. Follow logs\n'
        printf '  3. %s\n' "$previous_label"
        printf '  b. Back\n'
        ask choice "Select:"
        case "$choice" in
            1)
                $KUBECTL -n "$NAMESPACE" logs --all-containers --tail=200 "$pod" || true
                press_any
                return 0
                ;;
            2)
                note "Following logs for $pod. Press Ctrl+C to return to Fortify Lab."
                follow_pod_logs_safe "$pod" 100 || true
                press_any
                return 0
                ;;
            3)
                $KUBECTL -n "$NAMESPACE" logs --all-containers --previous --tail=200 "$pod" || true
                press_any
                return 0
                ;;
            [Bb]|"") return 1 ;;
            *) error "Invalid selection." ;;
        esac
    done
}

logs_menu() {
    title "Pod logs"
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    if k8s_select_resource pod "Select a pod"; then
        pod_log_action_menu "$K8S_SELECTED_RESOURCE_NAME"
    fi
}

logs_for_prefix() {
    local prefix="$1" pods=()
    mapfile -t pods < <(k8s_resource_names pod "" "$prefix")
    case "${#pods[@]}" in
        0)
            note "No pods matching '$prefix' have appeared yet."
            press_any
            ;;
        1)
            pod_log_action_menu "${pods[0]}"
            ;;
        *)
            if k8s_select_resource pod "Select a pod" "" "$prefix"; then
                pod_log_action_menu "$K8S_SELECTED_RESOURCE_NAME"
            else
                note "No pod selected."
                press_any
            fi
            ;;
    esac
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

    # Each pod tail runs in a backgrounded subshell. The parent owns Ctrl+C
    # handling, terminates those subshells, waits for them, and restores the
    # previous interrupt trap before returning to the menu.
    cleanup_streams() {
        local p
        for p in "${pids[@]}"; do
            if command -v pkill >/dev/null 2>&1; then
                pkill -TERM -P "$p" 2>/dev/null || true
            fi
            kill -TERM "$p" 2>/dev/null
        done
        # Brief grace, then verify clean.
        sleep 0.3
        for p in "${pids[@]}"; do
            wait "$p" 2>/dev/null
        done
        pids=()
    }
    local saved_int_trap stream_interrupted=0
    saved_int_trap=$(trap -p INT || true)
    trap 'stream_interrupted=1; cleanup_streams' INT

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
              trap - INT TERM
              $KUBECTL -n "$NAMESPACE" logs --follow --all-containers --tail=20 \
                  --ignore-errors=true "$pod" 2>&1 \
              | grep --line-buffered -F -- "$filter" \
              | awk -v c="$color" -v r="$RESET" -v p="$short" \
                  '{ printf "%s[%s]%s %s\n", c, p, r, $0; fflush() }'
            ) &
        else
            (
              trap - INT TERM
              $KUBECTL -n "$NAMESPACE" logs --follow --all-containers --tail=20 \
                  --ignore-errors=true "$pod" 2>&1 \
              | awk -v c="$color" -v r="$RESET" -v p="$short" \
                  '{ printf "%s[%s]%s %s\n", c, p, r, $0; fflush() }'
            ) &
        fi
        pids+=("$!")
    done

    # Block until all backgrounded tails exit OR Ctrl+C trips the trap.
    wait || true
    cleanup_streams
    restore_int_trap "$saved_int_trap"
    if [ "$stream_interrupted" -eq 1 ]; then
        echo
        note "Stopped streaming logs."
    fi
}

credential_value_from_secret() {
    local secret="$1" key="$2" encoded
    cluster_reachable || { error "Cluster is not reachable."; return 1; }
    encoded=$($KUBECTL -n "$NAMESPACE" get secret "$secret" \
        -o "go-template={{ index .data \"$key\" }}" 2>/dev/null) || {
        error "Could not read secret $secret/$key."
        return 1
    }
    [ -n "$encoded" ] || { error "Secret value $secret/$key is empty or missing."; return 1; }
    printf '%s' "$encoded" | base64 -d
}

credential_present_label() {
    local secret="$1" key="$2"
    if cluster_reachable && secret_key_exists "$secret" "$key"; then
        printf '%savailable%s' "$GREEN" "$RESET"
    else
        printf '%sunavailable%s' "$YELLOW" "$RESET"
    fi
}

credential_reveal_once() {
    local label="$1" secret="$2" key="$3" confirmation
    title "Reveal credential once"
    cat <<EOF

  Credential: $label
  Source:     $secret/$key

  This may expose a password or token in your terminal scrollback or screen
  capture. The wizard will not write this value to logs, diagnostics, .env,
  or any file.

EOF
    ask confirmation "Type REVEAL to display this value once:"
    [ "$confirmation" = REVEAL ] || { note "Reveal cancelled."; press_any; return 1; }
    echo
    section "$label"
    credential_value_from_secret "$secret" "$key" || { press_any; return 1; }
    echo
    note "Press Enter to clear this screen and return to the credentials menu."
    read -r _
    clear
}

credential_reveal_menu() {
    local choice
    while true; do
        title "Reveal one credential"
        cat <<EOF

  1. LIM admin password
  2. LIM pool password
  3. ScanCentral SAST client auth token
  4. ScanCentral SAST worker auth token
  5. ScanCentral SAST SSC ControllerToken
  6. ScanCentral DAST service token
  7. ScanCentral DAST SSC service account password
  8. ScanCentral DAST database owner password
  9. ScanCentral DAST database standard user password

  b. Back
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) credential_reveal_once "LIM admin password" lim-admin-credentials password ;;
            2) credential_reveal_once "LIM pool password" lim-pool password ;;
            3) credential_reveal_once "ScanCentral SAST client auth token" fortify-secrets scancentral-client-auth-token ;;
            4) credential_reveal_once "ScanCentral SAST worker auth token" fortify-secrets scancentral-worker-auth-token ;;
            5) credential_reveal_once "ScanCentral SAST SSC ControllerToken" fortify-secrets scancentral-ssc-scancentral-ctrl-secret ;;
            6) credential_reveal_once "ScanCentral DAST service token" scdast-service-token service-token ;;
            7) credential_reveal_once "ScanCentral DAST SSC service account password" scdast-ssc-serviceaccount password ;;
            8) credential_reveal_once "ScanCentral DAST database owner password" scdast-db-owner password ;;
            9) credential_reveal_once "ScanCentral DAST database standard user password" scdast-db-standard password ;;
            [Bb]) return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

credential_retrieval_commands() {
    title "Credential retrieval commands"
    cat <<EOF

  Use these commands when you prefer to retrieve a value yourself. Values are
  decoded from Kubernetes Secrets and are not written by the wizard.

  LIM admin password:
    $KUBECTL -n $NAMESPACE get secret lim-admin-credentials -o go-template='{{ index .data "password" }}' | base64 -d

  LIM pool password:
    $KUBECTL -n $NAMESPACE get secret lim-pool -o go-template='{{ index .data "password" }}' | base64 -d

  SAST client auth token:
    $KUBECTL -n $NAMESPACE get secret fortify-secrets -o go-template='{{ index .data "scancentral-client-auth-token" }}' | base64 -d

  SAST worker auth token:
    $KUBECTL -n $NAMESPACE get secret fortify-secrets -o go-template='{{ index .data "scancentral-worker-auth-token" }}' | base64 -d

  SAST SSC ControllerToken:
    $KUBECTL -n $NAMESPACE get secret fortify-secrets -o go-template='{{ index .data "scancentral-ssc-scancentral-ctrl-secret" }}' | base64 -d

  DAST service token:
    $KUBECTL -n $NAMESPACE get secret scdast-service-token -o go-template='{{ index .data "service-token" }}' | base64 -d

  DAST SSC service account password:
    $KUBECTL -n $NAMESPACE get secret scdast-ssc-serviceaccount -o go-template='{{ index .data "password" }}' | base64 -d

EOF
    press_any
}

certificate_trust_handoff() {
    title "Certificate trust"
    cat <<EOF

  mkcert root CA:
    ${ROOTCA_CERT:-$FORTIFY_CERTS/rootCA.pem}

  Import the mkcert root CA into each client machine or browser trust store
  that will access the lab URLs. FortifyLab serves workload TLS from the
  Kubernetes Secret $NAMESPACE/tls and configures MicroK8s ingress to use it
  as the default certificate when the installed ingress addon supports that.

  Lab hostnames:
    ssc.$DOMAIN
    lim.$DOMAIN
    sast.$DOMAIN
    dast.$DOMAIN
    dashboard.$DOMAIN

EOF
    press_any
}

ssc_login_guidance() {
    title "SSC login guidance"
    cat <<EOF

  SSC URL:
    ${SSC_URL:-<unset>}

  Username:
    admin

  Password:
    Refer to the SSC documentation for the default administrator password.
    FortifyLab does not store or display that vendor default password.

  After first login, change the password inside SSC and store it in your own
  password manager.

EOF
    press_any
}

urls_creds_summary() {
    title "URLs & credentials"
    cat <<EOF

  Service URLs
    SSC             ${SSC_URL:-<unset>}
    LIM             ${LIM_URL:-<unset>}
    SAST controller ${SCSAST_CTRL_URL:-<unset>}
    DAST            ${SCDAST_URL:-<unset>}
    Dashboard       https://dashboard.$DOMAIN

  Login guidance
    SSC             admin / refer to the SSC documentation for the default password
    LIM             lim_admin / stored in lim-admin-credentials
    DAST            SSC user mapped to a DAST role
    Dashboard       generate a token from Kubernetes Dashboard access

  Credential availability
    LIM admin password              $(credential_present_label lim-admin-credentials password)
    LIM pool password               $(credential_present_label lim-pool password)
    SAST client auth token           $(credential_present_label fortify-secrets scancentral-client-auth-token)
    SAST worker auth token           $(credential_present_label fortify-secrets scancentral-worker-auth-token)
    SAST SSC ControllerToken         $(credential_present_label fortify-secrets scancentral-ssc-scancentral-ctrl-secret)
    DAST service token               $(credential_present_label scdast-service-token service-token)
    DAST SSC service account         $(credential_present_label scdast-ssc-serviceaccount password)

EOF
}

urls_creds() {
    local choice
    while true; do
        urls_creds_summary
        cat <<EOF
  1. Reveal one credential
  2. Show retrieval commands
  3. SSC login guidance
  4. Kubernetes Dashboard token menu
  5. Certificate trust instructions

  r. Return
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) credential_reveal_menu ;;
            2) credential_retrieval_commands ;;
            3) ssc_login_guidance ;;
            4) dashboard_access_menu ;;
            5) certificate_trust_handoff ;;
            [Rr]|"") return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

flight_plan_tool() {
    local tool root
    tool="$FORTIFY_HOME_K8S/scripts/tools/flight-plans.py"
    if [ ! -f "$tool" ]; then
        root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
        tool="$root/scripts/tools/flight-plans.py"
    fi
    python3 "$tool" "$@"
}

flight_plan_default_id() {
    flight_plan_tool default 2>/dev/null || printf '%s\n' fortify-26.2
}

flight_plan_selected_id() {
    printf '%s\n' "${FORTIFY_FLIGHT_PLAN:-$(flight_plan_default_id)}"
}

flight_plan_list_records() {
    flight_plan_tool list 2>/dev/null
}

flight_plan_status_label() {
    case "$1" in
        recommended) printf '%s\n' Recommended ;;
        known-good) printf '%s\n' Known-good ;;
        legacy) printf '%s\n' Legacy ;;
        deprecated) printf '%s\n' Deprecated ;;
        candidate) printf '%s\n' Candidate ;;
        *) printf '%s\n' "${1:-Unknown}" ;;
    esac
}

flight_plan_pending_value() {
    local key="$1" fallback="${2:-}" pair
    shift 2 || true
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] || continue
        printf '%s\n' "${pair#*=}"
        return 0
    done
    printf '%s\n' "$fallback"
}

flight_plan_alignment_summary() {
    local plan_id="${1:-$(flight_plan_selected_id)}" output rc=0 drift=0 unknown=0 overrides=0
    output=$(flight_plan_tool compare-env "$plan_id" --env-file "$ENV_FILE" 2>/dev/null) || rc=$?
    [ -n "$output" ] || { printf 'unknown\n'; return 0; }
    drift=$(printf '%s\n' "$output" | awk -F'\t' '$2=="drifted" {c++} END{print c+0}')
    unknown=$(printf '%s\n' "$output" | awk -F'\t' '$2=="unknown" {c++} END{print c+0}')
    if [ "$unknown" -gt 0 ]; then
        printf 'needs review\n'
    elif [ "$drift" -gt 0 ] || [ "$rc" -ne 0 ]; then
        overrides="$drift"
        printf 'mixed (%d override%s or drift%s)\n' "$overrides" "$([ "$overrides" -eq 1 ] || printf s)" "$([ "$overrides" -eq 1 ] || printf s)"
    else
        printf 'aligned\n'
    fi
}

flight_plan_current_status() {
    local plan_id="${1:-$(flight_plan_selected_id)}"
    printf '  Flight Plan:        %s\n' "$plan_id"
    printf '  Alignment:          %s\n' "$(flight_plan_alignment_summary "$plan_id")"
    printf '  Deployment profile: %s\n' "${GUIDED_DEPLOYMENT_PROFILE_LABEL:-$(guided_profile_label "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}")}"
}

flight_plan_show_comparison() {
    local plan_id="${1:-$(flight_plan_selected_id)}" output
    section "Flight Plan comparison"
    output=$(flight_plan_tool compare-env "$plan_id" --env-file "$ENV_FILE" 2>/dev/null || true)
    if [ -z "$output" ]; then
        error "Could not compare .env to Flight Plan $plan_id. Validate the catalog."
        return 1
    fi
    printf '  %-36s %-18s %-22s %s\n' "Key" "State" "Expected" "Current"
    printf '%s\n' "$output" | while IFS=$'\t' read -r key state expected current; do
        printf '  %-36s %-18s %-22s %s\n' "$key" "$state" "$expected" "$current"
    done
    cat <<'EOF'

Rollback note:
  Restoring a previous .env backup is configuration rollback only. It does not
  downgrade application data, database schemas, or persistent volumes.
EOF
}

flight_plan_stage_updates() {
    local array_name="$1" plan_id="$2" line
    local -n pending_ref="$array_name"
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        env_pending_set "$array_name" "${line%%=*}" "${line#*=}"
    done < <(flight_plan_tool env-updates "$plan_id")
    env_pending_set "$array_name" FORTIFY_FLIGHT_PLAN "$plan_id"
}

flight_plan_select_menu() {
    local array_name="$1" records=() record choice plan_id label status family idx
    local -n pending_ref="$array_name"
    mapfile -t records < <(flight_plan_list_records)
    [ "${#records[@]}" -gt 0 ] || { error "No usable Flight Plans found. Validate config/flight-plans.toml."; press_any; return 1; }
    while true; do
        title "Select Fortify Flight Plan"
        printf '\nCurrent: %s\nPending: %s\n\n' "$(flight_plan_selected_id)" "$(flight_plan_pending_value FORTIFY_FLIGHT_PLAN '<none>' "${pending_ref[@]}")"
        section "Available Flight Plans"
        for idx in "${!records[@]}"; do
            IFS=$'\t' read -r plan_id label status family <<<"${records[$idx]}"
            printf '  %2d. %-18s %-13s %s\n' "$((idx + 1))" "$label" "$(flight_plan_status_label "$status")" "family $family"
        done
        cat <<'EOF'

  p. Preview pending changes
  b. Back
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            [Bb]|"") return 0 ;;
            [Pp]) [ "${#pending_ref[@]}" -gt 0 ] && env_preview_changes "${pending_ref[@]}" || note "No pending changes."; press_any ;;
            ''|*[!0-9]*) error "Select a Flight Plan number shown above."; sleep 1 ;;
            *)
                if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#records[@]}" ]; then
                    error "Out of range"; sleep 1; continue
                fi
                IFS=$'\t' read -r plan_id label status family <<<"${records[$((choice - 1))]}"
                flight_plan_stage_updates "$array_name" "$plan_id"
                note "Flight Plan staged: $label"
                cat <<'EOF'

Safety note:
  Flight Plan changes update version settings. Downgrades do not restore app
  data, database schemas, or persistent volumes. Use backups or a full lab reset
  when moving backward after a deployment has run.
EOF
                press_any
                return 0
                ;;
        esac
    done
}

flight_plan_discovery_menu() {
    local family output
    title "Flight Plan Discovery"
    cat <<'EOF'

Repo-owner workflow:
  Discover -> Draft -> Review -> Test -> Promote -> Commit

Discovery queries Docker Hub for known Fortify repositories and writes a
candidate TOML file. It does not update config/flight-plans.toml and is not
shown to normal users until the repo owner promotes it.
EOF
    echo
    ask family "Fortify family to discover, for example 26.2 or 25:" 
    [ -n "$family" ] || return 0
    output="$FORTIFY_HOME_K8S/tmp/flight-plan-candidates/fortify-$family.toml"
    flight_plan_tool discover --family "$family" --output "$output"
    press_any
}

flight_plan_versions_menu() {
    local choice pending_updates=()
    while true; do
        title "Deployment Versions"
        cat <<'EOF'

Purpose
  Choose a Fortify Flight Plan or override individual component versions.
EOF
        section "Current configuration"
        flight_plan_current_status
        section "Fortify components"
        grep -E '^\s*export\s+FORTIFY_(SSC|SCSAST|SCDAST|LIM|FLIGHT_PLAN)' "$ENV_FILE" 2>/dev/null | sed 's/^\s*export\s*/  /' || true
        section "Database versions"
        grep -E '^\s*export\s+FORTIFY_(MYSQL|POSTGRES)' "$ENV_FILE" 2>/dev/null | sed 's/^\s*export\s*/  /' || true
        cat <<'EOF'

Impact
  Flight Plans align Fortify product versions. MySQL and PostgreSQL are managed
  separately because application upgrades and database rollback are different risks.

Options
  1. Select Fortify Flight Plan
  2. Override individual Fortify component versions
  3. Manage database versions
  4. Compare .env to selected Flight Plan
  5. Discover candidate Flight Plan tags (repo owner)
  6. Preview pending .env changes
  7. Apply pending version changes

  r. Return
  q. Quit safely
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) flight_plan_select_menu pending_updates ;;
            2) env_guided_section_editor "Individual Fortify component versions" versions || return $? ;;
            3) env_guided_section_editor "Database versions" database_versions || return $? ;;
            4) flight_plan_show_comparison; press_any ;;
            5) flight_plan_discovery_menu ;;
            6) [ "${#pending_updates[@]}" -gt 0 ] && env_preview_changes "${pending_updates[@]}" || note "No pending changes."; press_any ;;
            7) env_section_apply_pending flight-plan pending_updates; press_any ;;
            [Rr]) env_section_prompt_return pending_updates && return 0 ;;
            [Qq]) env_section_prompt_return pending_updates && return 130 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

versions_menu() {
    flight_plan_versions_menu
}

fcli_path_entry_present() {
    local target="$1"
    case ":$PATH:" in
        *":$target:"*) return 0 ;;
        *) return 1 ;;
    esac
}

fcli_export_current_path() {
    local target="${1:-$FORTIFY_FCLI_INSTALL_DIR}"
    [ -d "$target" ] || return 1
    if fcli_path_entry_present "$target"; then
        return 0
    fi
    export PATH="$target:$PATH"
}

fcli_shell_profile_path() {
    if [ -n "${FORTIFY_FCLI_PROFILE_FILE:-}" ]; then
        printf '%s\n' "$FORTIFY_FCLI_PROFILE_FILE"
    elif [ -f "$HOME/.bashrc" ] || [ "${SHELL##*/}" = bash ]; then
        printf '%s/.bashrc\n' "$HOME"
    else
        printf '%s/.profile\n' "$HOME"
    fi
}

fcli_profile_has_path() {
    local profile="$1" target="${2:-$FORTIFY_FCLI_INSTALL_DIR}"
    [ -f "$profile" ] || return 1
    grep -F "$target" "$profile" >/dev/null 2>&1
}

fcli_persist_path() {
    local target="${1:-$FORTIFY_FCLI_INSTALL_DIR}" profile
    profile="$(fcli_shell_profile_path)"
    mkdir -p "$(dirname "$profile")" || return 1
    if fcli_profile_has_path "$profile" "$target"; then
        return 0
    fi
    {
        printf '\n# FortifyLab tools\n'
        printf 'export PATH="%s:$PATH"\n' "$target"
    } >> "$profile"
}


fcli_truststore_path() {
    local truststore="${TRUSTSTORE:-}"
    if [ -z "$truststore" ]; then
        truststore="${FORTIFY_CERTS:-$FORTIFY_HOME_K8S/certs}/truststore"
    fi
    printf '%s\n' "$truststore"
}

fcli_trust_configured_current() {
    local truststore="${1:-$(fcli_truststore_path)}"
    [ "${FCLI_TRUSTSTORE:-}" = "$truststore" ] &&
        [ "${FCLI_TRUSTSTORE_TYPE:-}" = "JKS" ] &&
        [ -n "${FCLI_TRUSTSTORE_PWD:-}" ]
}

fcli_export_lab_trust() {
    local truststore="${1:-$(fcli_truststore_path)}"
    [ -s "$truststore" ] || return 1
    [ -n "${DEFAULT_PASS:-}" ] || return 2
    export FCLI_TRUSTSTORE="$truststore"
    export FCLI_TRUSTSTORE_TYPE="JKS"
    export FCLI_TRUSTSTORE_PWD="$DEFAULT_PASS"
}

fcli_profile_has_lab_trust_hints() {
    local profile="$1" truststore="${2:-$(fcli_truststore_path)}"
    [ -f "$profile" ] || return 1
    grep -F "export FCLI_TRUSTSTORE=\"$truststore\"" "$profile" >/dev/null 2>&1 &&
        grep -F 'export FCLI_TRUSTSTORE_TYPE="JKS"' "$profile" >/dev/null 2>&1
}

fcli_persist_lab_trust_hints() {
    local truststore="${1:-$(fcli_truststore_path)}" profile
    [ -s "$truststore" ] || return 1
    profile="$(fcli_shell_profile_path)"
    mkdir -p "$(dirname "$profile")" || return 1
    if fcli_profile_has_lab_trust_hints "$profile" "$truststore"; then
        return 0
    fi
    {
        printf '\n# FortifyLab fcli TLS trust hints; set the truststore password privately per shell.\n'
        printf 'export FCLI_TRUSTSTORE="%s"\n' "$truststore"
        printf 'export FCLI_TRUSTSTORE_TYPE="JKS"\n'
    } >> "$profile"
}

fcli_configure_lab_trust() {
    local truststore="${1:-$(fcli_truststore_path)}" profile
    if [ ! -s "$truststore" ]; then
        error "Lab truststore not found at $truststore. Generate TLS certificates first."
        return 1
    fi
    if [ -z "${DEFAULT_PASS:-}" ]; then
        error "DEFAULT_PASS is required to activate fcli lab TLS trust for this shell."
        return 1
    fi
    fcli_export_lab_trust "$truststore" || return 1
    fcli_persist_lab_trust_hints "$truststore" || return 1
    profile="$(fcli_shell_profile_path)"
    note "Activated fcli lab TLS trust for this shell."
    note "Persisted non-secret truststore hints in $profile."
    note "For future shells, export FCLI_TRUSTSTORE_PWD from DEFAULT_PASS in a private shell."
}

fcli_trust_status_line() {
    local truststore
    truststore="$(fcli_truststore_path)"
    if [ ! -s "$truststore" ]; then
        printf '%s Lab truststore missing at %s\n' "$WARN_MARK" "$truststore"
    elif fcli_trust_configured_current "$truststore"; then
        printf '%s FCLI lab TLS trust active for %s\n' "$OK_MARK" "$truststore"
    else
        printf '%s Lab truststore exists but fcli trust env is not active\n' "$WARN_MARK"
    fi
}

fcli_path() {
    command -v fcli 2>/dev/null && return 0
    if [ -x "$FORTIFY_FCLI_INSTALL_DIR/fcli" ]; then
        printf '%s\n' "$FORTIFY_FCLI_INSTALL_DIR/fcli"
        return 0
    fi
    return 1
}

fcli_installed_version() {
    local path
    path="$(fcli_path)" || return 1
    "$path" --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1
}

fcli_status_line() {
    local path version
    path=$(fcli_path || true)
    if [ -z "$path" ]; then
        printf '%s FCLI missing; recommended %s\n' "$WARN_MARK" "$FORTIFY_RECOMMENDED_FCLI_VERSION"
        return 0
    fi
    version=$(fcli_installed_version || true)
    if [ "$version" = "$FORTIFY_RECOMMENDED_FCLI_VERSION" ]; then
        printf '%s FCLI %s at %s\n' "$OK_MARK" "$version" "$path"
    elif [ -n "$version" ]; then
        printf '%s FCLI %s at %s; recommended %s\n' "$WARN_MARK" "$version" "$path" "$FORTIFY_RECOMMENDED_FCLI_VERSION"
    else
        printf '%s FCLI found at %s; version unknown; recommended %s\n' "$WARN_MARK" "$path" "$FORTIFY_RECOMMENDED_FCLI_VERSION"
    fi
}

fcli_print_status() {
    section "FCLI status"
    printf '  Recommended version: %s\n' "$FORTIFY_RECOMMENDED_FCLI_VERSION"
    printf '  Install directory:    %s\n' "$FORTIFY_FCLI_INSTALL_DIR"
    printf '  %s\n' "$(fcli_status_line)"
    printf '  %s\n' "$(fcli_trust_status_line)"
    cat <<EOF

  FCLI is needed only for local Fortify command-line workflows after the lab is
  running. Missing or mismatched FCLI does not block infrastructure deployment.
EOF
}

fcli_install_or_update() {
    local version="${FORTIFY_RECOMMENDED_FCLI_VERSION}" target="$FORTIFY_FCLI_INSTALL_DIR"
    local archive checksum temp_dir url checksum_url expected actual
    if [ -z "$version" ]; then
        error "FORTIFY_RECOMMENDED_FCLI_VERSION is empty."
        return 1
    fi
    command -v curl >/dev/null 2>&1 || { error "curl is required to download FCLI."; return 1; }
    command -v tar >/dev/null 2>&1 || { error "tar is required to extract FCLI."; return 1; }
    command -v sha256sum >/dev/null 2>&1 || { error "sha256sum is required to verify FCLI."; return 1; }
    temp_dir=$(mktemp -d) || return 1
    archive="$temp_dir/fcli-linux.tgz"
    checksum="$temp_dir/fcli-linux.tgz.sha256"
    url="https://github.com/fortify/fcli/releases/download/v${version}/fcli-linux.tgz"
    checksum_url="${url}.sha256"
    note "Downloading FCLI $version from the Fortify GitHub release assets."
    if ! curl -fsSL "$url" -o "$archive" || ! curl -fsSL "$checksum_url" -o "$checksum"; then
        rm -rf "$temp_dir"
        error "Could not download FCLI $version. Check network access and FORTIFY_RECOMMENDED_FCLI_VERSION."
        return 1
    fi
    expected=$(awk '{print $1; exit}' "$checksum")
    actual=$(sha256sum "$archive" | awk '{print $1; exit}')
    if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
        rm -rf "$temp_dir"
        error "FCLI checksum verification failed."
        return 1
    fi
    mkdir -p "$target" || { rm -rf "$temp_dir"; return 1; }
    tar -xzf "$archive" -C "$target" fcli fcli_completion || {
        rm -rf "$temp_dir"
        error "Could not extract FCLI into $target."
        return 1
    }
    chmod 755 "$target/fcli" 2>/dev/null || true
    rm -rf "$temp_dir"
    note "Installed FCLI $version into $target."
    if fcli_export_current_path "$target"; then
        note "Added FCLI to the current shell PATH."
    fi
    if fcli_persist_path "$target"; then
        note "Persisted the FCLI PATH handoff in $(fcli_shell_profile_path)."
    fi
    if [ -s "$(fcli_truststore_path)" ]; then
        fcli_configure_lab_trust "$(fcli_truststore_path)" || return 1
    else
        note "Generate TLS certificates before configuring fcli lab TLS trust."
    fi
}

fcli_print_command_templates() {
    local ssc_url="${SSC_URL:-https://ssc.${DOMAIN:-fortifydemo.com}}"
    local sast_url="${SCSAST_CTRL_URL:-https://sast.${DOMAIN:-fortifydemo.com}/scancentral-ctrl/}"
    cat <<EOF

SSC-first FCLI templates

  # Create a temporary SSC/FCLI session. Paste token values only when fcli asks,
  # or replace placeholders in a private shell. Do not save filled commands.
  fcli ssc session login --url "$ssc_url" --sc-sast-url "$sast_url" --token='<SSC_TOKEN_OR_PROMPT>' --client-auth-token='<SCANCENTRAL_CLIENT_AUTH_TOKEN>' --ssc-session=fortifylab

  # Inspect the intended SSC application version before any scan submission.
  fcli ssc appversion get '<APP_VERSION_NAME_OR_ID>' --ssc-session=fortifylab

  # Later scan submission starts from a prebuilt package or MBS file; this
  # readiness menu intentionally does not build sample apps or submit scans.
  fcli sc-sast scan start --file='<PACKAGE_OR_MBS_FILE>' --publish-to='<APP_VERSION_NAME_OR_ID>' --ssc-session=fortifylab

  fcli ssc session logout --ssc-session=fortifylab

FoD optional templates

  fcli fod session login --url='<FOD_URL>' --tenant='<FOD_TENANT>' --client-id='<FOD_CLIENT_ID>' --client-secret='<FOD_CLIENT_SECRET>' --fod-session=fortifylab-fod
  fcli fod release get '<FOD_RELEASE_ID_OR_NAME>' --fod-session=fortifylab-fod
  fcli fod session logout --fod-session=fortifylab-fod

EOF
}

fcli_tools_menu() {
    local choice
    while true; do
        title "Tools and FCLI readiness"
        fcli_print_status
        cat <<EOF

  1. Install or update FCLI to the recommended version
  2. Configure fcli trust for lab TLS
  3. Show FCLI status
  4. Show secret-safe command templates

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) fcli_install_or_update; press_any ;;
            2) fcli_configure_lab_trust; press_any ;;
            3) fcli_print_status; press_any ;;
            4) fcli_print_command_templates; press_any ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


env_is_secret_key() {
    case "$1" in
        *PASS*|*PASSWORD*|*TOKEN*|*SECRET*|*KEY*|*LICENSE*|*CREDENTIAL*) return 0 ;;
        *) return 1 ;;
    esac
}

python_config_available() {
    command -v python3 >/dev/null 2>&1 &&
        [ -x "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" ] &&
        [ -s "${ENV_FILE:-}" ]
}

python_config_diagnostics() {
    python_config_available || return 1
    "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" config diagnostics --env "$ENV_FILE"
}

python_config_validate() {
    python_config_available || return 1
    "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" config validate --env "$ENV_FILE"
}

python_config_repair_domain_urls() {
    python_config_available || return 1
    "${FORTIFY_HOME_K8S:-.}/bin/fortifylab" config repair-derived --env "$ENV_FILE" --apply
}

env_display_value() {
    local key="$1" value="${2:-}"
    if env_is_secret_key "$key"; then
        [ -n "$value" ] && printf '%s\n' '<redacted>' || printf '%s\n' '<unset>'
    else
        printf '%s\n' "${value:-<unset>}"
    fi
}

env_shell_quote() {
    local value="$1"
    printf "'%s'" "${value//\'/\'\\\'\'}"
}

env_assignment_expr() {
    local key="$1" value="$2" mode="${3:-literal}"
    if [ "$mode" = expr ]; then
        printf 'export %s="%s"' "$key" "$value"
    else
        printf 'export %s=%s' "$key" "$(env_shell_quote "$value")"
    fi
}

env_backup_timestamp() { date +%Y%m%d-%H%M%S; }

env_prepare_backup() {
    local reason="${1:-wizard-edit}" timestamp backup meta
    timestamp=$(env_backup_timestamp)
    mkdir -p "$ENV_BACKUP_DIR" || return 1
    backup="$ENV_BACKUP_DIR/.env.$timestamp.$reason.bak"
    meta="$ENV_BACKUP_DIR/.env.$timestamp.$reason.meta"
    cp "$ENV_FILE" "$backup" || return 1
    ENV_LAST_BACKUP="$backup"
    ENV_LAST_BACKUP_META="$meta"
    printf 'created_by=fortifylab-wizard\ncreated_at=%s\nreason=%s\n' "$timestamp" "$reason" >"$meta"
    printf '%s\n' "$backup" >"$FORTIFY_HOME_K8S/.env.rollback"
}

env_current_value() {
    local key="$1"
    ( set -a; source "$ENV_FILE" >/dev/null 2>&1; printf '%s\n' "${!key:-}" )
}

env_apply_updates() {
    local reason="$1" key value mode pair changed_keys=() tmp line
    shift
    [ -s "$ENV_FILE" ] || { error "$ENV_FILE does not exist or is empty."; return 1; }
    [ "$#" -gt 0 ] || { note "No changes selected."; return 0; }
    env_prepare_backup "$reason" || { error "Could not create .env backup."; return 1; }
    tmp="$FORTIFY_HOME_K8S/.env.tmp"
    cp "$ENV_FILE" "$tmp" || return 1
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        mode=literal
        case "$value" in
            __EXPR__*) mode=expr; value="${value#__EXPR__}" ;;
        esac
        line=$(env_assignment_expr "$key" "$value" "$mode")
        awk -v key="$key" -v newline="$line" '
            BEGIN { replaced = 0 }
            $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "=" { print newline; replaced = 1; next }
            { print }
            END { if (!replaced) { print ""; print newline } }
        ' "$tmp" >"$tmp.next" || return 1
        mv "$tmp.next" "$tmp" || return 1
        changed_keys+=("$key")
    done
    mv "$tmp" "$ENV_FILE" || return 1
    {
        printf 'changed_keys='
        local sep=""
        for key in "${changed_keys[@]}"; do
            printf '%s%s' "$sep" "$key"
            sep=,
        done
        printf '\n'
    } >>"$ENV_LAST_BACKUP_META"
    wizard_log_event "action=env_update reason=$reason backup=$(basename "$ENV_LAST_BACKUP") keys=${changed_keys[*]}"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    note "Updated .env. Backup: $ENV_LAST_BACKUP"
    section "Changed keys"
    for key in "${changed_keys[@]}"; do
        printf '  - %s\n' "$key"
    done
}

env_preview_changes() {
    local key new mode old display_old display_new pair
    for pair in "$@"; do
        key="${pair%%=*}"
        new="${pair#*=}"
        mode=literal
        case "$new" in
            __EXPR__*) mode=expr; new="${new#__EXPR__}" ;;
        esac
        old=$(env_current_value "$key")
        if [ "$mode" = expr ]; then
            display_new="$new"
        else
            display_new="$new"
        fi
        display_old=$(env_display_value "$key" "$old")
        display_new=$(env_display_value "$key" "$display_new")
        printf '  %-32s %s -> %s\n' "$key" "$display_old" "$display_new"
    done
}

env_backup_files() {
    find "$ENV_BACKUP_DIR" -maxdepth 1 -type f -name '.env.*.bak' 2>/dev/null | sort -r
}

env_restore_backup() {
    local backup="$1" reason="${2:-restore}"
    [ -s "$backup" ] || { error "Backup not found: $backup"; return 1; }
    env_prepare_backup "before-$reason" || return 1
    cp "$backup" "$ENV_FILE" || return 1
    wizard_log_event "action=env_restore restored=$(basename "$backup") rollback=$(basename "$ENV_LAST_BACKUP")"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    note "Restored .env from $backup"
}

env_rollback_last() {
    local backup
    if [ -s "$FORTIFY_HOME_K8S/.env.rollback" ]; then
        backup=$(cat "$FORTIFY_HOME_K8S/.env.rollback")
    else
        backup=$(env_backup_files | head -n 1)
    fi
    [ -n "${backup:-}" ] || { error "No .env backups are available."; return 1; }
    env_restore_backup "$backup" rollback-last
}

env_restore_selected() {
    local backups=() choice idx
    while IFS= read -r choice; do backups+=("$choice"); done < <(env_backup_files)
    [ "${#backups[@]}" -gt 0 ] || { error "No .env backups are available."; press_any; return 1; }
    section "Available .env backups"
    for idx in "${!backups[@]}"; do
        printf '  %d. %s\n' $((idx + 1)) "${backups[$idx]}"
    done
    echo
    ask choice "Restore which backup number (or empty to cancel):"
    [ -z "$choice" ] && return 0
    [[ "$choice" =~ ^[0-9]+$ ]] || { error "Invalid selection"; return 1; }
    [ "$choice" -ge 1 ] && [ "$choice" -le "${#backups[@]}" ] || { error "Out of range"; return 1; }
    env_restore_backup "${backups[$((choice - 1))]}" restore-selected
}

env_section_keys() {
    case "$1" in
        identity) printf '%s\n' NAMESPACE ;;
        urls) printf '%s\n' SSC LIM SCDAST SCSAST SSC_URL LIM_URL LIM_API_URL SCDAST_URL SCSAST_URL SCSAST_CTRL_URL ;;
        versions) printf '%s\n' FORTIFY_FLIGHT_PLAN FORTIFY_SSC_CHART_VERSION FORTIFY_SSC_IMAGE_TAG FORTIFY_SCSAST_CHART_VERSION FORTIFY_SCSAST_CTRL_IMAGE_TAG FORTIFY_SCSAST_WORKER_IMAGE_TAG FORTIFY_SCDAST_CHART_VERSION FORTIFY_LIM_CHART_VERSION ;;
        database_versions) printf '%s\n' FORTIFY_MYSQL_CHART_VERSION FORTIFY_POSTGRES_CHART_VERSION FORTIFY_POSTGRES_IMAGE_TAG FORTIFY_MYSQL_IMAGE_TAG ;;
        credentials) printf '%s\n' DEFAULT_PASS SCDAST_SSC_USER SCDAST_SSC_PASS SCDAST_DB_OWNER_USER SCDAST_DB_OWNER_PASS SCDAST_DB_STANDARD_USER SCDAST_DB_STANDARD_PASS LIM_POOL_NAME LIM_POOL_PASS ;;
        *) return 1 ;;
    esac
}


deployment_version_cache_dir() {
    printf '%s\n' "${FORTIFY_HOME_K8S:-.}/.fortifylab/version-cache"
}

deployment_version_recommended_value() {
    local key="$1"
    sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$key=\"?([^\"]*)\"?[[:space:]]*$/\2/p" "$FORTIFY_HOME_K8S/.env.example" 2>/dev/null | tail -n 1
}

deployment_version_repo_for_key() {
    case "$1" in
        FORTIFY_SSC_CHART_VERSION) printf '%s\n' fortifydocker/helm-ssc ;;
        FORTIFY_SSC_IMAGE_TAG) printf '%s\n' fortifydocker/ssc-webapp ;;
        FORTIFY_SCSAST_CHART_VERSION) printf '%s\n' fortifydocker/helm-scancentral-sast ;;
        FORTIFY_SCDAST_CHART_VERSION) printf '%s\n' fortifydocker/helm-scancentral-dast-core ;;
        FORTIFY_LIM_CHART_VERSION) printf '%s\n' fortifydocker/helm-lim ;;
        FORTIFY_MYSQL_CHART_VERSION) printf '%s\n' bitnamicharts/mysql ;;
        FORTIFY_POSTGRES_CHART_VERSION) printf '%s\n' bitnamicharts/postgresql ;;
        FORTIFY_MYSQL_IMAGE_TAG) printf '%s\n' bitnamilegacy/mysql ;;
        FORTIFY_POSTGRES_IMAGE_TAG) printf '%s\n' bitnamilegacy/postgresql ;;
        *) return 1 ;;
    esac
}

deployment_version_cached_latest() {
    local key="$1" file
    file="$(deployment_version_cache_dir)/$key.latest"
    [ -s "$file" ] && sed -n '1p' "$file"
}

deployment_version_cache_latest() {
    local key="$1" value="$2" dir
    [ -n "$value" ] || return 0
    dir=$(deployment_version_cache_dir)
    mkdir -p "$dir" || return 0
    printf '%s\n' "$value" >"$dir/$key.latest" 2>/dev/null || true
}

deployment_version_query_dockerhub_latest() {
    local repo="$1"
    command -v curl >/dev/null 2>&1 || return 1
    command -v python3 >/dev/null 2>&1 || return 1
    curl -fsSL "https://registry.hub.docker.com/v2/repositories/$repo/tags?page_size=25&ordering=last_updated" 2>/dev/null | python3 -c '
import json, re, sys
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(1)
for item in data.get("results", []):
    name=item.get("name", "")
    if name and name != "latest" and re.search(r"[0-9]", name):
        print(name)
        sys.exit(0)
sys.exit(1)
'
}

deployment_version_latest_for_key() {
    local key="$1" repo latest
    repo=$(deployment_version_repo_for_key "$key" 2>/dev/null) || return 1
    latest=$(deployment_version_query_dockerhub_latest "$repo" 2>/dev/null || true)
    if [ -n "$latest" ]; then
        deployment_version_cache_latest "$key" "$latest"
        printf '%s\n' "$latest"
        return 0
    fi
    deployment_version_cached_latest "$key"
}

deployment_versions_status() {
    local key current recommended cached repo
    section "Deployment version guidance"
    printf '  %-36s %-20s %-20s %-20s\n' "Key" "Current" "Recommended" "Cached/latest"
    while IFS= read -r key; do
        current=$(env_current_value "$key")
        recommended=$(deployment_version_recommended_value "$key")
        cached=$(deployment_version_cached_latest "$key")
        repo=$(deployment_version_repo_for_key "$key" 2>/dev/null || true)
        [ -n "$cached" ] || cached="<not checked>"
        [ -n "$recommended" ] || recommended="<unknown>"
        printf '  %-36s %-20s %-20s %-20s\n' "$key" "${current:-<unset>}" "$recommended" "$cached"
        [ -n "$repo" ] || printf '    note: no online source is mapped for %s; use manual entry.\n' "$key"
    done < <(env_section_keys versions)
    cat <<'EOF'

Use 'u' in the Deployment versions editor to check available Docker Hub tags.
Newest available is not automatically compatible; review Fortify release notes
and database upgrade boundaries before applying version changes.
EOF
}

deployment_versions_discover_into() {
    local array_name="$1" key latest found=0 keys=()
    section "Checking available deployment versions"
    mapfile -t keys < <(env_section_keys versions)
    for key in "${keys[@]}"; do
        latest=$(deployment_version_latest_for_key "$key" 2>/dev/null || true)
        if [ -n "$latest" ]; then
            printf '  %-36s latest available: %s
' "$key" "$latest"
            if confirm "Queue $key=$latest?"; then
                env_pending_set "$array_name" "$key" "$latest"
            fi
            found=1
        else
            printf '  %-36s no online value found; use manual entry.
' "$key"
        fi
    done
    [ "$found" -eq 1 ] || note "No online version data was available. Manual entry remains available by selecting a numbered field."
}

env_pending_value() {
    local key="$1" fallback="${2:-}" pair
    shift 2 || true
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] || continue
        printf '%s\n' "${pair#*=}"
        return 0
    done
    printf '%s\n' "$fallback"
}

env_pending_has_key() {
    local key="$1" pair
    shift
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] && return 0
    done
    return 1
}

env_pending_set() {
    local array_name="$1" key="$2" value="$3" pair updated=0 next=()
    local -n pending_ref="$array_name"
    for pair in "${pending_ref[@]}"; do
        if [ "${pair%%=*}" = "$key" ]; then
            next+=("$key=$value")
            updated=1
        else
            next+=("$pair")
        fi
    done
    [ "$updated" -eq 1 ] || next+=("$key=$value")
    pending_ref=("${next[@]}")
}

env_section_editor_row() {
    local idx="$1" key="$2" current pending display_current display_pending marker=""
    shift 2
    current=$(env_current_value "$key")
    pending=$(env_pending_value "$key" "$current" "$@")
    display_current=$(env_display_value "$key" "$current")
    display_pending=$(env_display_value "$key" "$pending")
    if env_pending_has_key "$key" "$@"; then
        marker="*"
        printf '  %2d. %-32s %s -> %s %s\n' "$idx" "$key" "$display_current" "$display_pending" "$marker"
    else
        printf '  %2d. %-32s %s\n' "$idx" "$key" "$display_current"
    fi
}

env_edit_section_field() {
    local key="$1" array_name="$2" current value
    local -n pending_ref="$array_name"
    current=$(env_current_value "$key")
    printf '\n%s [%s]\n' "$key" "$(env_display_value "$key" "$current")"
    if env_is_secret_key "$key"; then
        read -rsp "New value (empty to keep current): " value
        echo
    else
        read -rp "New value (empty to keep current): " value
    fi
    [ -n "$value" ] || { note "No change queued."; return 0; }
    env_pending_set "$array_name" "$key" "$value"
    note "Queued change for $key."
}

env_section_apply_pending() {
    local reason="$1" array_name="$2"
    local -n pending_ref="$array_name"
    [ "${#pending_ref[@]}" -gt 0 ] || { note "No pending changes to apply."; return 0; }
    section "Pending .env changes"
    env_preview_changes "${pending_ref[@]}"
    echo
    if confirm "Apply these .env changes with a backup first?"; then
        env_apply_updates "$reason" "${pending_ref[@]}" || return 1
        pending_ref=()
        echo
        if confirm "Roll back this change now?"; then
            env_rollback_last
        fi
    else
        note "Configuration changes remain pending."
    fi
}

env_section_validate() {
    local reason="$1"
    case "$reason" in
        urls) env_diagnostics ;;
        versions) deployment_versions_status ;;
        *)
            if env_config_valid; then
                note "Configuration host and URL values look valid."
            else
                env_config_issue_lines | awk '{ printf "  - %s\n", $0 }'
            fi
            ;;
    esac
}

env_section_prompt_return() {
    local array_name="$1"
    local -n pending_ref="$array_name"
    [ "${#pending_ref[@]}" -eq 0 ] && return 0
    confirm "Discard pending changes and return?"
}

env_guided_section_editor() {
    local section_name="$1" reason="$2" choice idx key keys=() pending_updates=()
    while true; do
        title "Configuration editor"
        section "$section_name"
        mapfile -t keys < <(env_section_keys "$reason")
        for idx in "${!keys[@]}"; do
            env_section_editor_row "$((idx + 1))" "${keys[$idx]}" "${pending_updates[@]}"
        done
        cat <<EOF

  p. Preview pending changes
  a. Apply pending changes
  d. Discard pending changes
  v. Validate / show guidance
EOF
        if [ "$reason" = versions ]; then
            printf "  u. Check available versions\n"
        fi
        cat <<EOF
  r. Return
  q. Quit safely
EOF
        echo
        ask choice "Select field or action:"
        case "$choice" in
            [0-9]*)
                if [ "$choice" -ge 1 ] && [ "$choice" -le "${#keys[@]}" ]; then
                    key="${keys[$((choice - 1))]}"
                    env_edit_section_field "$key" pending_updates
                else
                    error "Out of range"; sleep 1
                fi
                ;;
            [Pp])
                if [ "${#pending_updates[@]}" -gt 0 ]; then
                    section "Pending .env changes"
                    env_preview_changes "${pending_updates[@]}"
                else
                    note "No pending changes."
                fi
                press_any
                ;;
            [Aa]) env_section_apply_pending "$reason" pending_updates; press_any ;;
            [Dd]) pending_updates=(); note "Pending changes discarded."; press_any ;;
            [Vv]) env_section_validate "$reason"; press_any ;;
            [Uu])
                if [ "$reason" = versions ]; then
                    deployment_versions_discover_into pending_updates
                    press_any
                else
                    error "Invalid"; sleep 1
                fi
                ;;
            [Rr]) env_section_prompt_return pending_updates && return 0 ;;
            [Qq]) env_section_prompt_return pending_updates && return 130 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

env_valid_domain() {
    [[ "$1" =~ ^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)+$ ]]
}

env_url_host() {
    local url="$1"
    printf '%s\n' "$url" | sed -n -E 's#^https://([^/:]+)([:/].*)?$#\1#p'
}

env_expected_host_for_key() {
    local key="$1" domain="${DOMAIN:-fortifydemo.com}"
    case "$key" in
        SSC) printf 'ssc.%s\n' "$domain" ;;
        LIM) printf 'lim.%s\n' "$domain" ;;
        SCDAST) printf 'dast.%s\n' "$domain" ;;
        SCSAST) printf 'sast.%s\n' "$domain" ;;
        *) return 1 ;;
    esac
}

env_expected_url_for_key() {
    local key="$1" domain="${DOMAIN:-fortifydemo.com}"
    case "$key" in
        SSC_URL) printf 'https://ssc.%s\n' "$domain" ;;
        LIM_URL) printf 'https://lim.%s\n' "$domain" ;;
        LIM_API_URL) printf 'https://lim.%s/LIM.API\n' "$domain" ;;
        SCDAST_URL) printf 'https://dast.%s\n' "$domain" ;;
        SCSAST_URL) printf 'https://sast.%s\n' "$domain" ;;
        SCSAST_CTRL_URL) printf 'https://sast.%s/scancentral-ctrl/\n' "$domain" ;;
        *) return 1 ;;
    esac
}

env_placeholder_like() {
    [[ "${1:-}" =~ ^[A-Z][A-Z0-9_]*$ ]]
}

env_config_issue_lines() {
    local issue=0 key value url_key host_key host url_host expected
    if [ -z "${DOMAIN:-}" ] || ! env_valid_domain "${DOMAIN:-}"; then
        printf 'DOMAIN must be a lowercase DNS-style domain such as fortifydemo.com.\n'
        issue=1
    fi
    for key in SSC LIM SCDAST SCSAST; do
        value="${!key:-}"
        expected=$(env_expected_host_for_key "$key" || true)
        if [ -z "$value" ]; then
            printf '%s is unset; expected %s.\n' "$key" "$expected"
            issue=1
        elif env_placeholder_like "$value"; then
            printf '%s is set to placeholder-like value %s; expected %s.\n' "$key" "$value" "$expected"
            issue=1
        elif ! env_valid_domain "$value"; then
            printf '%s must be a lowercase DNS hostname with at least one dot; current value is %s; expected %s.\n' "$key" "$value" "$expected"
            issue=1
        elif [ -n "$expected" ] && [ "$value" != "$expected" ]; then
            printf '%s is %s; expected derived value %s for DOMAIN=%s.\n' "$key" "$value" "$expected" "${DOMAIN:-<unset>}"
            issue=1
        fi
    done
    for pair in SSC_URL:SSC LIM_URL:LIM LIM_API_URL:LIM SCDAST_URL:SCDAST SCSAST_URL:SCSAST SCSAST_CTRL_URL:SCSAST; do
        url_key="${pair%%:*}"
        host_key="${pair#*:}"
        value="${!url_key:-}"
        host="${!host_key:-}"
        expected=$(env_expected_url_for_key "$url_key" || true)
        if [ -z "$value" ]; then
            printf '%s is unset; expected %s.\n' "$url_key" "$expected"
            issue=1
            continue
        fi
        if env_placeholder_like "$value"; then
            printf '%s is set to placeholder-like value %s; expected %s.\n' "$url_key" "$value" "$expected"
            issue=1
            continue
        fi
        url_host=$(env_url_host "$value")
        if [ -z "$url_host" ]; then
            printf '%s must be an https URL; current value is %s; expected %s.\n' "$url_key" "$value" "$expected"
            issue=1
        elif [ -n "$host" ] && ! env_placeholder_like "$host" && [ "$url_host" != "$host" ]; then
            printf '%s host %s does not match %s=%s; expected %s.\n' "$url_key" "$url_host" "$host_key" "$host" "$expected"
            issue=1
        elif [ -n "$expected" ] && [ "$value" != "$expected" ]; then
            printf '%s is %s; expected derived value %s for DOMAIN=%s.\n' "$url_key" "$value" "$expected" "${DOMAIN:-<unset>}"
            issue=1
        fi
    done
    [ "$issue" -eq 0 ]
}

env_config_valid() {
    [ -z "$(env_config_issue_lines)" ]
}

deployment_config_guard() {
    local issues
    if python_config_available; then
        python_config_validate && return 0
        printf '%s\n' 'Use Configuration editor -> Repair derived host and URL values from DOMAIN, or edit .env manually, then retry.'
        return 1
    fi
    issues=$(env_config_issue_lines)
    [ -z "$issues" ] && return 0
    error "Configuration has invalid host or URL values; deployment is blocked before Kubernetes changes."
    printf '%s\n' "$issues" | awk '{ printf "  - %s\n", $0 }'
    printf '%s\n' 'Use Configuration editor -> Repair derived host and URL values from DOMAIN, or edit .env manually, then retry.'
    if [ -t 0 ] && confirm "Repair derived host and URL values from DOMAIN now?"; then
        env_repair_domain_urls --yes
        printf '%s\n' 'Repair applied. Retry the start operation.'
    fi
    return 1
}

app_start_config_guard() {
    local idx="$1" step="${APP_GUIDED_STEP[$idx]:-}"
    case "$step" in
        ssc|lim|sast|dast) deployment_config_guard ;;
        *) return 0 ;;
    esac
}

env_repair_domain_urls() {
    local assume_yes="${1:-}" domain updates=()
    if [ "$assume_yes" = "--yes" ] && python_config_available; then
        python_config_repair_domain_urls
        return $?
    fi
    domain="${DOMAIN:-fortifydemo.com}"
    domain="${domain,,}"
    env_valid_domain "$domain" || { error "Cannot repair from invalid DOMAIN=${DOMAIN:-<unset>}. Set DOMAIN to a lowercase DNS-style domain first."; return 1; }
    while IFS= read -r line; do updates+=("$line"); done < <(domain_url_updates "$domain")
    section "Repair derived host and URL values"
    env_preview_changes "${updates[@]}"
    echo
    if [ "$assume_yes" = "--yes" ] || confirm "Apply these repaired values with a backup first?"; then
        env_apply_updates repair-domain-url "${updates[@]}"
    else
        note "Repair cancelled."
    fi
}

env_diagnostics() {
    local key raw effective expected issues rc=0
    if python_config_available; then
        python_config_diagnostics || rc=$?
        flight_plan_show_comparison "$(flight_plan_selected_id)" || rc=$?
        return "$rc"
    fi
    title "Configuration diagnostics"
    printf '\n.env file: %s\n' "$ENV_FILE"
    printf 'DOMAIN:   %s\n' "${DOMAIN:-<unset>}"
    section "Host and URL values"
    for key in SSC LIM SCDAST SCSAST SSC_URL LIM_URL LIM_API_URL SCDAST_URL SCSAST_URL SCSAST_CTRL_URL; do
        raw=$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$key=(.*)$/\2/p" "$ENV_FILE" 2>/dev/null | tail -n 1)
        effective="${!key:-<unset>}"
        expected=$(env_expected_host_for_key "$key" 2>/dev/null || env_expected_url_for_key "$key" 2>/dev/null || true)
        printf '  %-16s raw=%-36s effective=%-36s expected=%s\n' "$key" "${raw:-<missing>}" "$effective" "${expected:-<none>}"
    done
    section "Issues"
    issues=$(env_config_issue_lines || true)
    if [ -z "$issues" ]; then
        printf '  No host/URL configuration drift detected.\n'
    else
        printf '%s\n' "$issues" | awk '{ printf "  - %s\n", $0 }'
    fi
    flight_plan_show_comparison "$(flight_plan_selected_id)" || return $?
    return 0
}

domain_url_updates() {
    local domain="$1"
    printf '%s\n' \
        "DOMAIN=$domain" \
        'SSC=__EXPR__ssc.$DOMAIN' \
        'LIM=__EXPR__lim.$DOMAIN' \
        'SCDAST=__EXPR__dast.$DOMAIN' \
        'SCSAST=__EXPR__sast.$DOMAIN' \
        'SSC_URL=__EXPR__https://$SSC' \
        'LIM_URL=__EXPR__https://$LIM' \
        'LIM_API_URL=__EXPR__https://$LIM/LIM.API' \
        'SCDAST_URL=__EXPR__https://$SCDAST' \
        'SCSAST_URL=__EXPR__https://$SCSAST' \
        'SCSAST_CTRL_URL=__EXPR__https://$SCSAST/scancentral-ctrl/'
}

domain_url_assistant() {
    local domain updates=()
    title "Domain and URL assistant"
    printf '\nCurrent domain: %s\n\n' "${DOMAIN:-<unset>}"
    ask domain "New base domain, for example fortifydemo.com:"
    [ -n "$domain" ] || return 0
    domain=${domain,,}
    env_valid_domain "$domain" || { error "Use a lowercase DNS-style domain such as fortifydemo.com or lab.example.internal."; press_any; return 1; }
    while IFS= read -r line; do updates+=("$line"); done < <(domain_url_updates "$domain")
    section "Pending domain and URL changes"
    env_preview_changes "${updates[@]}"
    cat <<EOF

Impact after applying:
  - Regenerate TLS certificates.
  - Refresh Kubernetes Secrets.
  - Reapply ingress resources or restart affected apps.
  - Update client DNS or /etc/hosts for the new hostnames.
  - Import or trust the mkcert root CA on client browsers if needed.
EOF
    echo
    if confirm "Apply domain and URL changes with a backup first?"; then
        env_apply_updates domain-url "${updates[@]}"
    else
        note "Domain changes cancelled."
    fi
    press_any
}

mkcert_caroot_path() {
    mkcert -CAROOT 2>/dev/null
}

mkcert_root_ca_source() {
    local caroot
    caroot=$(mkcert_caroot_path) || return 1
    [ -n "$caroot" ] || return 1
    printf '%s/rootCA.pem\n' "$caroot"
}

mkcert_root_ca_export() {
    local src dest="$FORTIFY_HOME_K8S/certs/rootCA.pem"
    command -v mkcert >/dev/null 2>&1 || { error "mkcert is not installed."; return 1; }
    src=$(mkcert_root_ca_source) || { error "Could not locate mkcert CAROOT."; return 1; }
    [ -s "$src" ] || { error "mkcert rootCA.pem not found at $src. Run certificate generation first."; return 1; }
    mkdir -p "$(dirname "$dest")" || return 1
    cp "$src" "$dest" || return 1
    wizard_log_event "action=mkcert_root_ca_export destination=$dest"
    note "Copied public mkcert root CA to $dest"
    note "Only the public root CA certificate was copied; the private CA key was not touched."
}

mkcert_trust_instructions() {
    cat <<'EOF'

Trust the exported public root CA on client machines that open the lab URLs.
Never import, copy, or share the mkcert private CA key.

Windows:
  1. Open Manage user certificates.
  2. Import rootCA.pem into Trusted Root Certification Authorities.

macOS:
  1. Open Keychain Access.
  2. Import rootCA.pem into System or login keychain.
  3. Set the certificate to Always Trust for SSL.

Ubuntu/Debian:
  sudo cp rootCA.pem /usr/local/share/ca-certificates/fortifylab-mkcert.crt
  sudo update-ca-certificates

Firefox/NSS stores:
  Import rootCA.pem in Settings -> Privacy & Security -> Certificates,
  or use certutil for the relevant browser profile.
EOF
}

mkcert_root_ca_menu() {
    local src
    title "mkcert root CA"
    if command -v mkcert >/dev/null 2>&1; then
        src=$(mkcert_root_ca_source || true)
        printf '\n  mkcert CAROOT rootCA.pem: %s\n' "${src:-<unavailable>}"
        printf '  Export target:           %s\n' "$FORTIFY_HOME_K8S/certs/rootCA.pem"
    else
        printf '\n  mkcert is not installed. Install prerequisites first.\n'
    fi
    cat <<EOF

  1. Export public rootCA.pem to certs/rootCA.pem
  2. Show trust instructions

  r. Return
EOF
    echo
    ask choice "Select:"
    case "$choice" in
        1) mkcert_root_ca_export; mkcert_trust_instructions; press_any ;;
        2) mkcert_trust_instructions; press_any ;;
        [Rr]) return ;;
        *) error "Invalid"; sleep 1 ;;
    esac
}

raw_edit_env() {
    env_prepare_backup raw-editor || { error "Could not create .env backup."; return 1; }
    "${EDITOR:-nano}" "$ENV_FILE"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
}

edit_env() {
    local choice
    while true; do
        title "Configuration editor"
        cat <<EOF

  Lab Settings
    1. Kubernetes namespace
    2. Change lab domain and derived URLs

  Deployment Settings
    3. Deployment versions
    4. Credentials, users, and passwords
    5. Advanced service URLs

  Validation and Repair
    6. Validate configuration
    7. Repair derived URLs from domain

  Certificates and Trust
    8. Export root CA and trust instructions

  Backups and Advanced
    9. Roll back last .env change
    10. Restore selected .env backup
    11. Open raw .env editor

  q. Quit safely
  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) env_guided_section_editor "Kubernetes namespace" identity || return $? ;;
            2) domain_url_assistant ;;
            3) flight_plan_versions_menu || return $? ;;
            4) env_guided_section_editor "Credentials, users, and passwords" credentials || return $? ;;
            5) env_guided_section_editor "Advanced service URLs" urls || return $? ;;
            6) env_diagnostics; press_any ;;
            7) env_repair_domain_urls; press_any ;;
            8) mkcert_root_ca_menu ;;
            9) env_rollback_last; press_any ;;
            10) env_restore_selected; press_any ;;
            11) raw_edit_env; press_any ;;
            [Qq]) clear; exit 0 ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


# ============================================================
# Prerequisites menu
# ============================================================

prereqs_menu() {
    while true; do
        title "Install prerequisites"
        echo
        prereqs_status_table
        echo
        echo "  1. JDK 17 (apt)"
        echo "  2. Docker (apt) + docker login"
        echo "  3. mkcert (apt)"
        echo "  4. microk8s (snap) + addons (dns, ingress, nfs, dashboard, community)"
        echo "  5. All of the above"
        echo "  g. Restart wizard with microk8s group access"
        echo
        echo "  r. Return"
        echo
        ask choice "Select:"

        case "$choice" in
            1) install_jdk;        prereqs_install_summary ;;
            2) install_docker;     prereqs_install_summary ;;
            3) install_mkcert;     prereqs_install_summary ;;
            4) install_microk8s;   prereqs_install_summary ;;
            5) install_jdk; install_docker; install_mkcert; install_microk8s; prereqs_install_summary ;;
            [Gg]) restart_with_microk8s_group ;;
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
  5. Configuration editor (.env, domain, root CA)
  6. Cluster profiles and remote readiness
  7. Setup readiness summary

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
            6) cluster_profile_menu ;;
            7) setup_menu ;;
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

ensure_registry_credentials() {
    case "$1" in
        mysql|postgresql|ssc|lim|sast|dast)
            refresh_registry_credentials
            ;;
    esac
}
install_microk8s() {
    if command -v microk8s &>/dev/null; then
        note "Already installed."
    else
        bash "$FORTIFY_HOME_K8S/scripts/install_microk8s.sh"
    fi
    if microk8s_access_ready; then
        note "MicroK8s access is active in this shell."
    else
        note "MicroK8s installed, but this shell does not have group access yet."
        note "Choose g to restart the wizard with microk8s group access, or run: newgrp microk8s"
    fi
}

prereq_status() {
    if "$@"; then
        printf '%s ready' "$OK_MARK"
    else
        printf '%s needs attention' "$WARN_MARK"
    fi
}

docker_ready() {
    command -v docker >/dev/null 2>&1 || return 1
    [ -s "$HOME/.docker/config.json" ] || return 1
}

mkcert_ready() { command -v mkcert >/dev/null 2>&1; }
java_ready() { command -v java >/dev/null 2>&1 && command -v keytool >/dev/null 2>&1; }

microk8s_access_ready() {
    command -v microk8s >/dev/null 2>&1 || return 1
    id -nG | grep -qw microk8s || return 1
    microk8s status --wait-ready >/dev/null 2>&1 || return 1
}

prereqs_status_table() {
    printf '  %-24s %s\n' "JDK 17" "$(prereq_status java_ready)"
    printf '  %-24s %s\n' "Docker + login" "$(prereq_status docker_ready)"
    printf '  %-24s %s\n' "mkcert" "$(prereq_status mkcert_ready)"
    printf '  %-24s %s\n' "MicroK8s access" "$(prereq_status microk8s_access_ready)"
}

prereqs_ready_count() {
    local ready=0
    java_ready && ready=$((ready + 1))
    docker_ready && ready=$((ready + 1))
    mkcert_ready && ready=$((ready + 1))
    microk8s_access_ready && ready=$((ready + 1))
    printf '%s\n' "$ready"
}

prereqs_install_summary() {
    local ready
    ready=$(prereqs_ready_count)
    printf '\n'
    note "Host prerequisites: $ready/4 ready."
    if [ "$ready" -eq 4 ]; then
        note "All prerequisite indicators are complete."
    elif ! microk8s_access_ready && command -v microk8s >/dev/null 2>&1; then
        note "Next missing: MicroK8s group access in this shell."
        note "Choose g to restart the wizard with group access, or run: newgrp microk8s"
    fi
    press_any
}
restart_with_microk8s_group() {
    local restart_command
    command -v microk8s >/dev/null 2>&1 || {
        error "MicroK8s is not installed yet."
        press_any
        return 1
    }
    if microk8s_access_ready; then
        note "MicroK8s group access is already active."
        press_any
        return 0
    fi
    if command -v sg >/dev/null 2>&1; then
        note "Restarting wizard with microk8s group access..."
        printf -v restart_command '%q --accept-lab-use' "$FORTIFY_HOME_K8S/start_wizard.sh"
        exec sg microk8s -c "$restart_command"
    fi
    error "Could not find sg to refresh group access automatically."
    note "Run this in your shell, then relaunch the wizard: newgrp microk8s"
    press_any
}
