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
ENV_BACKUP_DIR="$FORTIFY_HOME_K8S/.env.backups"


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
FORTIFY_RECOMMENDED_MEMORY_GIB="${FORTIFY_RECOMMENDED_MEMORY_GIB:-16}"
FORTIFY_RECOMMENDED_DISK_GIB="${FORTIFY_RECOMMENDED_DISK_GIB:-50}"
FORTIFY_RECOMMENDED_FCLI_VERSION="${FORTIFY_RECOMMENDED_FCLI_VERSION:-3.23.3}"
FORTIFY_FCLI_INSTALL_DIR="${FORTIFY_FCLI_INSTALL_DIR:-$HOME/fortify/tools/bin}"

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
# shellcheck source=scripts/lib/registry-credentials.sh
source "$FORTIFY_HOME_K8S/scripts/lib/registry-credentials.sh"
# shellcheck source=scripts/lib/wizard-logging.sh
source "$FORTIFY_HOME_K8S/scripts/lib/wizard-logging.sh"
# shellcheck source=scripts/lib/coredns-lab-hosts.sh
source "$FORTIFY_HOME_K8S/scripts/lib/coredns-lab-hosts.sh"


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
            note "Use Advanced setup -> Configuration editor to set your domain, passwords, and image versions."
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

APP_LABEL=("MySQL" "PostgreSQL" "SSC" "LIM" "ScanCentral SAST" "ScanCentral DAST" "Juice Shop" "WebGoat" "DVWA")
APP_PODS=("mysql"  "postgresql" "ssc-webapp" "lim" "scancentral-sast" "sdast" "sample-juice-shop" "sample-webgoat" "sample-dvwa")
APP_URL_VAR=(""    ""           "SSC_URL"    "LIM_URL" "SCSAST_CTRL_URL" "SCDAST_URL" "JUICE_SHOP_URL" "WEBGOAT_URL" "DVWA_URL")
APP_GUIDED_STEP=("mysql" "postgresql" "ssc" "lim" "sast" "dast" "sample_juice_shop" "sample_webgoat" "sample_dvwa")
APP_SAMPLE=(0 0 0 0 0 0 1 1 1)
APP_START=(
    "apps/mysql/start.sh"
    "apps/postgresql/start.sh"
    "apps/ssc/start.sh"
    "apps/lim/start.sh"
    "apps/scsast/start.sh"
    "apps/scdast/core/start.sh apps/scdast/scanner/start.sh"
    "apps/samples/juice-shop/start.sh"
    "apps/samples/webgoat/start.sh"
    "apps/samples/dvwa/start.sh"
)
APP_STOP=(
    "apps/mysql/stop.sh"
    "apps/postgresql/stop.sh"
    "apps/ssc/stop.sh"
    "apps/lim/stop.sh"
    "apps/scsast/stop.sh"
    "apps/scdast/core/stop.sh apps/scdast/scanner/stop.sh"
    "apps/samples/juice-shop/stop.sh"
    "apps/samples/webgoat/stop.sh"
    "apps/samples/dvwa/stop.sh"
)
APP_DESTROY=(
    "apps/mysql/destroy.sh"
    "apps/postgresql/destroy.sh"
    "apps/ssc/destroy.sh"
    "apps/lim/destroy.sh"
    "apps/scsast/destroy.sh"
    "apps/scdast/core/destroy.sh apps/scdast/scanner/destroy.sh"
    "apps/samples/juice-shop/destroy.sh"
    "apps/samples/webgoat/destroy.sh"
    "apps/samples/dvwa/destroy.sh"
)

app_index_is_sample() {
    [ "${APP_SAMPLE[$1]:-0}" -eq 1 ]
}

app_index_in_full_lifecycle() {
    ! app_index_is_sample "$1"
}

sample_default_url_for_var() {
    local variable="$1" domain="${DOMAIN:-fortifydemo.com}"
    case "$variable" in
        JUICE_SHOP_URL) printf '%s\n' "https://juice-shop.$domain" ;;
        WEBGOAT_URL) printf '%s\n' "https://webgoat.$domain" ;;
        DVWA_URL) printf '%s\n' "https://dvwa.$domain" ;;
        *) return 1 ;;
    esac
}

app_url_for_index() {
    local idx="$1" variable="" value=""
    variable="${APP_URL_VAR[$idx]:-}"
    [ -n "$variable" ] || return 0
    value="${!variable:-}"
    if [ -z "$value" ]; then
        value="$(sample_default_url_for_var "$variable" 2>/dev/null || true)"
    fi
    printf '%s\n' "$value"
}

app_url_display_for_index() {
    local idx="$1" variable="" value=""
    variable="${APP_URL_VAR[$idx]:-}"
    [ -n "$variable" ] || return 0
    value=$(app_url_for_index "$idx")
    [ -n "$value" ] || return 0
    if [[ "$value" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
        printf '<invalid: %s=%s>\n' "$variable" "$value"
    else
        printf '%s\n' "$value"
    fi
}


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
                note "Following logs for $pod. Press Ctrl+C to return."
                $KUBECTL -n "$NAMESPACE" logs --all-containers --follow --tail=100 "$pod" || true
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

fcli_path() {
    command -v fcli 2>/dev/null
}

fcli_installed_version() {
    command -v fcli >/dev/null 2>&1 || return 1
    fcli --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1
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
    note "Add this directory to PATH if fcli is not found: export PATH=\"$target:\$PATH\""
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
  2. Show FCLI status
  3. Show secret-safe command templates

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) fcli_install_or_update; press_any ;;
            2) fcli_print_status; press_any ;;
            3) fcli_print_command_templates; press_any ;;
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
        identity) printf '%s\n' NAMESPACE DOMAIN ;;
        urls) printf '%s\n' SSC LIM SCDAST SCSAST SSC_URL LIM_URL LIM_API_URL SCDAST_URL SCSAST_URL SCSAST_CTRL_URL ;;
        versions) printf '%s\n' FORTIFY_SSC_CHART_VERSION FORTIFY_SSC_IMAGE_TAG FORTIFY_SCSAST_CHART_VERSION FORTIFY_SCSAST_CTRL_IMAGE_TAG FORTIFY_SCSAST_WORKER_IMAGE_TAG FORTIFY_SCDAST_CHART_VERSION FORTIFY_LIM_CHART_VERSION FORTIFY_MYSQL_CHART_VERSION FORTIFY_POSTGRES_CHART_VERSION FORTIFY_POSTGRES_IMAGE_TAG FORTIFY_MYSQL_IMAGE_TAG ;;
        credentials) printf '%s\n' DEFAULT_PASS SCDAST_SSC_USER SCDAST_SSC_PASS SCDAST_DB_OWNER_USER SCDAST_DB_OWNER_PASS SCDAST_DB_STANDARD_USER SCDAST_DB_STANDARD_PASS LIM_POOL_NAME LIM_POOL_PASS ;;
        *) return 1 ;;
    esac
}

env_guided_section_editor() {
    local section_name="$1" reason="$2" key current value updates=()
    title "Configuration editor"
    section "$section_name"
    while IFS= read -r key; do
        current=$(env_current_value "$key")
        printf '\n%s [%s]\n' "$key" "$(env_display_value "$key" "$current")"
        if env_is_secret_key "$key"; then
            read -rsp "New value (empty to keep current): " value
            echo
        else
            read -rp "New value (empty to keep current): " value
        fi
        [ -z "$value" ] && continue
        updates+=("$key=$value")
    done < <(env_section_keys "$reason")
    [ "${#updates[@]}" -gt 0 ] || { note "No changes selected."; press_any; return 0; }
    section "Pending .env changes"
    env_preview_changes "${updates[@]}"
    echo
    if confirm "Apply these .env changes with a backup first?"; then
        env_apply_updates "$reason" "${updates[@]}"
    else
        note "Configuration changes cancelled."
    fi
    press_any
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
    local key raw effective expected issues
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

  1. Lab identity and domain
  2. URLs
  3. Image/chart versions
  4. Credentials and passwords
  5. Domain and URL assistant
  6. Configuration diagnostics
  7. Repair derived host and URL values from DOMAIN
  8. mkcert root CA export and trust help
  9. Roll back last wizard .env change
  10. Restore selected .env backup
  11. Open raw .env in editor (backup first)

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) env_guided_section_editor "Lab identity and domain" identity ;;
            2) env_guided_section_editor "URLs" urls ;;
            3) env_guided_section_editor "Image/chart versions" versions ;;
            4) env_guided_section_editor "Credentials and passwords" credentials ;;
            5) domain_url_assistant ;;
            6) env_diagnostics; press_any ;;
            7) env_repair_domain_urls; press_any ;;
            8) mkcert_root_ca_menu ;;
            9) env_rollback_last; press_any ;;
            10) env_restore_selected; press_any ;;
            11) raw_edit_env; press_any ;;
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



# ============================================================
# Deployment steps shared by Guided and Express modes
# ============================================================

GUIDED_ALL_STEP_ID=("prereqs" "inputs" "preflight" "certs" "dashboard" "secrets" "mysql" "postgresql" "ssc" "lim" "sast_controller" "sast_sensor" "dast_core" "dast_scanner" "sample_juice_shop" "sample_webgoat" "sample_dvwa" "configure")
GUIDED_ALL_STEP_LABEL=("Host prerequisites" "Configuration and license" "Deployment pre-flight" "TLS certificates" "Kubernetes Dashboard" "Kubernetes Secrets" "MySQL" "PostgreSQL" "Software Security Center" "LIM" "ScanCentral SAST Controller" "ScanCentral SAST Sensor" "ScanCentral DAST Core" "ScanCentral DAST Scanner" "Juice Shop" "WebGoat" "DVWA" "Post-deploy configuration")
GUIDED_ALL_STEP_OPTIONAL=(1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1)
GUIDED_ALL_STEP_DURATION=("5-15 min" "2-5 min" "<1 min" "1-2 min" "2-5 min" "<1 min" "3-8 min" "3-8 min" "5-15 min" "3-8 min" "5-15 min" "3-8 min" "5-15 min" "5-15 min" "1-3 min" "1-3 min" "1-3 min" "manual")
GUIDED_ALL_STEP_IMPACT=("host packages/add-ons" "local configuration" "read-only" "creates/updates lab TLS" "applies Dashboard" "creates/updates Secrets" "applies MySQL" "applies PostgreSQL" "applies SSC" "applies LIM" "applies SAST controller" "applies SAST sensor" "applies DAST Core" "applies DAST scanner" "applies intentionally vulnerable sample app" "applies intentionally vulnerable sample app" "applies intentionally vulnerable sample app" "manual configuration")
GUIDED_ALL_STEP_TIMEOUT=(900 300 120 180 300 60 600 600 900 600 900 600 1200 900 300 300 300 0)
GUIDED_ALL_STEP_MANUAL=(0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1)
GUIDED_ALL_STEP_PROBE=("prereqs_complete" "inputs_complete" "preflight_inputs_complete" "certs_ready" "dashboard_ready" "secrets_ready" "mysql_ready" "postgresql_ready" "ssc_ready" "lim_ready" "sast_controller_ready" "sast_sensor_ready" "dast_core_ready" "dast_scanner_ready" "sample_juice_shop_ready" "sample_webgoat_ready" "sample_dvwa_ready" "configure_ready")
GUIDED_ALL_STEP_HELP=(
    "Install the host tools and MicroK8s add-ons used by the lab."
    "Review .env and provide a readable Fortify license before deployment."
    "Validate cluster readiness, storage, registry login, capacity, and required settings without changing the cluster."
    "Create the local CA and wildcard TLS material. Existing certificates are reused."
    "Deploy the default operational Web UI early so you can watch later workloads."
    "Create the Kubernetes credentials and application configuration. Secrets are never saved as wizard state."
    "Deploy MySQL and verify it accepts an authenticated query before SSC."
    "Deploy PostgreSQL and verify it accepts an authenticated query before DAST."
    "Deploy SSC after the MySQL dependency gate passes. SSC does not require ScanCentral SAST."
    "Deploy LIM and wait for its application endpoint."
    "Deploy the ScanCentral SAST controller. It can run without SSC unless you choose an integrated SAST profile."
    "Deploy a ScanCentral SAST sensor only after the SAST controller is present."
    "Deploy DAST Core after its database and license dependencies are ready."
    "Deploy a DAST scanner only after DAST Core is ready."
    "Deploy OWASP Juice Shop as an intentionally vulnerable lab target. Do not expose it outside an isolated lab."
    "Deploy OWASP WebGoat as an intentionally vulnerable lab target. Do not expose it outside an isolated lab."
    "Deploy DVWA as an intentionally vulnerable lab target. Do not expose it outside an isolated lab."
    "Configure DNS, SSC/SAST integration tokens, and the LIM pool when you are ready."
)

GUIDED_STEP_ID=()
GUIDED_STEP_LABEL=()
GUIDED_STEP_OPTIONAL=()
GUIDED_STEP_DURATION=()
GUIDED_STEP_IMPACT=()
GUIDED_STEP_TIMEOUT=()
GUIDED_STEP_MANUAL=()
GUIDED_STEP_PROBE=()
GUIDED_STEP_HELP=()
GUIDED_DEPLOYMENT_PROFILE="${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
GUIDED_DEPLOYMENT_PROFILE_LABEL="Full lab"
GUIDED_DEPLOYMENT_COMPONENTS="full_lab"

GUIDED_AUTO_ADVANCE="${GUIDED_AUTO_ADVANCE:-0}"
GUIDED_AUTO_ADVANCE_DELAY="${GUIDED_AUTO_ADVANCE_DELAY:-5}"
GUIDED_WAIT_INTERVAL="${GUIDED_WAIT_INTERVAL:-5}"
GUIDED_WAIT_LAST_FAILURE=""
GUIDED_WAIT_LAST_STATE=""
GUIDED_MODE_CONTEXT="${GUIDED_MODE_CONTEXT:-fresh}"

GUIDED_PREFLIGHT_MODE_ID=("fresh" "resume" "component")
GUIDED_PREFLIGHT_MODE_CONTRACT=(
    "fresh: read-only preflight plus empty managed-release guard before deployment"
    "resume: read-only preflight; existing managed releases are expected and live state selects the first gap"
    "component: read-only preflight; existing managed releases are allowed for expert start/upgrade repair"
)

guided_all_step_index() {
    local wanted="$1" idx
    for idx in "${!GUIDED_ALL_STEP_ID[@]}"; do
        [ "${GUIDED_ALL_STEP_ID[$idx]}" = "$wanted" ] && { printf '%s\n' "$idx"; return 0; }
    done
    return 1
}

guided_profile_label() {
    case "$1" in
        ssc_only) printf '%s\n' "SSC only" ;;
        sast_standalone) printf '%s\n' "SAST standalone" ;;
        sast_full) printf '%s\n' "SAST full with SSC" ;;
        dast_full) printf '%s\n' "DAST full" ;;
        full_lab) printf '%s\n' "Full lab" ;;
        custom) printf '%s\n' "Custom" ;;
        *) printf '%s\n' "Full lab" ;;
    esac
}

guided_profile_components_for() {
    case "$1" in
        ssc_only) printf '%s\n' "ssc" ;;
        sast_standalone) printf '%s\n' "sast_controller" ;;
        sast_full) printf '%s\n' "ssc sast_controller sast_sensor" ;;
        dast_full) printf '%s\n' "ssc lim dast_core dast_scanner" ;;
        full_lab) printf '%s\n' "ssc lim sast_controller sast_sensor dast_core dast_scanner" ;;
        custom) printf '%s\n' "${GUIDED_DEPLOYMENT_COMPONENTS:-${FORTIFY_DEPLOYMENT_COMPONENTS:-}}" ;;
        *) printf '%s\n' "ssc lim sast_controller sast_sensor dast_core dast_scanner" ;;
    esac
}

guided_component_selected() {
    local wanted="$1" component
    for component in $GUIDED_DEPLOYMENT_COMPONENTS; do
        [ "$component" = "$wanted" ] && return 0
    done
    return 1
}

guided_add_component() {
    local component="$1"
    guided_component_selected "$component" || GUIDED_DEPLOYMENT_COMPONENTS="${GUIDED_DEPLOYMENT_COMPONENTS:+$GUIDED_DEPLOYMENT_COMPONENTS }$component"
}

guided_expand_deployment_components() {
    local changed=1
    while [ "$changed" -eq 1 ]; do
        changed=0
        if guided_component_selected ssc && ! guided_component_selected mysql; then guided_add_component mysql; changed=1; fi
        if guided_component_selected sast_sensor && ! guided_component_selected sast_controller; then guided_add_component sast_controller; changed=1; fi
        if guided_component_selected sast_full; then guided_add_component ssc; guided_add_component sast_controller; guided_add_component sast_sensor; changed=1; fi
        if guided_component_selected dast_core; then
            for dep in postgresql lim ssc; do guided_component_selected "$dep" || { guided_add_component "$dep"; changed=1; }; done
        fi
        if guided_component_selected dast_scanner && ! guided_component_selected dast_core; then guided_add_component dast_core; changed=1; fi
        if guided_component_selected full_lab; then
            for dep in ssc lim sast_controller sast_sensor dast_core dast_scanner; do guided_component_selected "$dep" || { guided_add_component "$dep"; changed=1; }; done
        fi
        if guided_component_selected sample_apps; then
            for dep in sample_juice_shop sample_webgoat sample_dvwa; do guided_component_selected "$dep" || { guided_add_component "$dep"; changed=1; }; done
        fi
    done
}

guided_component_step_selected() {
    case "$1" in
        prereqs|inputs|preflight|certs|secrets|dashboard) return 0 ;;
        configure)
            guided_component_selected ssc || guided_component_selected sast_sensor || guided_component_selected dast_core || guided_component_selected dast_scanner
            ;;
        *) guided_component_selected "$1" ;;
    esac
}

guided_reset_active_steps() {
    GUIDED_STEP_ID=()
    GUIDED_STEP_LABEL=()
    GUIDED_STEP_OPTIONAL=()
    GUIDED_STEP_DURATION=()
    GUIDED_STEP_IMPACT=()
    GUIDED_STEP_TIMEOUT=()
    GUIDED_STEP_MANUAL=()
    GUIDED_STEP_PROBE=()
    GUIDED_STEP_HELP=()
}

guided_append_active_step() {
    local id="$1" idx
    idx=$(guided_all_step_index "$id") || return 1
    GUIDED_STEP_ID+=("${GUIDED_ALL_STEP_ID[$idx]}")
    GUIDED_STEP_LABEL+=("${GUIDED_ALL_STEP_LABEL[$idx]}")
    GUIDED_STEP_OPTIONAL+=("${GUIDED_ALL_STEP_OPTIONAL[$idx]}")
    GUIDED_STEP_DURATION+=("${GUIDED_ALL_STEP_DURATION[$idx]}")
    GUIDED_STEP_IMPACT+=("${GUIDED_ALL_STEP_IMPACT[$idx]}")
    GUIDED_STEP_TIMEOUT+=("${GUIDED_ALL_STEP_TIMEOUT[$idx]}")
    GUIDED_STEP_MANUAL+=("${GUIDED_ALL_STEP_MANUAL[$idx]}")
    GUIDED_STEP_PROBE+=("${GUIDED_ALL_STEP_PROBE[$idx]}")
    GUIDED_STEP_HELP+=("${GUIDED_ALL_STEP_HELP[$idx]}")
}

guided_apply_deployment_profile() {
    local profile="${1:-${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}}" id
    GUIDED_DEPLOYMENT_PROFILE="$profile"
    GUIDED_DEPLOYMENT_PROFILE_LABEL=$(guided_profile_label "$profile")
    GUIDED_DEPLOYMENT_COMPONENTS=$(guided_profile_components_for "$profile")
    guided_expand_deployment_components
    guided_reset_active_steps
    for id in "${GUIDED_ALL_STEP_ID[@]}"; do
        guided_component_step_selected "$id" && guided_append_active_step "$id"
    done
}

guided_print_profile_summary() {
    local component
    printf '  Profile: %s\n' "$GUIDED_DEPLOYMENT_PROFILE_LABEL"
    printf '  Components: '
    if [ -z "$GUIDED_DEPLOYMENT_COMPONENTS" ]; then
        printf 'platform only'
    else
        for component in $GUIDED_DEPLOYMENT_COMPONENTS; do printf '%s ' "$component"; done
    fi
    printf '\n'
}

guided_profile_save() {
    local profile="$1" components="${2:-}"
    if [ "$profile" = custom ]; then
        env_apply_updates deployment-profile "FORTIFY_DEPLOYMENT_PROFILE=$profile" "FORTIFY_DEPLOYMENT_COMPONENTS=$components"
    else
        env_apply_updates deployment-profile "FORTIFY_DEPLOYMENT_PROFILE=$profile" "FORTIFY_DEPLOYMENT_COMPONENTS="
    fi
    # shellcheck disable=SC1090
    [ -f "$ENV_FILE" ] && source "$ENV_FILE"
    guided_apply_deployment_profile "$profile"
}

guided_custom_component_prompt() {
    local components=""
    printf '\nChoose the capabilities you want. Dependencies are added automatically.\n'
    confirm "Include SSC?" && components="$components ssc"
    confirm "Include ScanCentral SAST controller?" && components="$components sast_controller"
    confirm "Include ScanCentral SAST sensor?" && components="$components sast_sensor"
    confirm "Include LIM?" && components="$components lim"
    confirm "Include ScanCentral DAST Core?" && components="$components dast_core"
    confirm "Include ScanCentral DAST scanner?" && components="$components dast_scanner"
    components=$(printf '%s\n' "$components" | xargs)
    [ -n "$components" ] || components=""
    GUIDED_DEPLOYMENT_COMPONENTS="$components"
    guided_expand_deployment_components
    printf '\nExpanded deployment plan:\n'
    guided_print_profile_summary
    if confirm "Save this custom profile to .env?"; then
        guided_profile_save custom "$GUIDED_DEPLOYMENT_COMPONENTS"
    else
        GUIDED_DEPLOYMENT_PROFILE=custom
        GUIDED_DEPLOYMENT_PROFILE_LABEL=$(guided_profile_label custom)
        guided_reset_active_steps
        local id
        for id in "${GUIDED_ALL_STEP_ID[@]}"; do
            guided_component_step_selected "$id" && guided_append_active_step "$id"
        done
        note "Using this custom profile for the current wizard session only."
    fi
}

guided_profile_menu() {
    local choice profile
    title "Deployment profile"
    printf '\nSelect the lab capabilities to deploy. The wizard automatically adds required dependencies; profile changes never stop or remove existing resources.\n\n'
    printf '  1. SSC only\n'
    printf '  2. SAST standalone (controller only)\n'
    printf '  3. SAST full with SSC (SSC + controller + sensor)\n'
    printf '  4. DAST full (SSC + LIM + DAST Core + scanner)\n'
    printf '  5. Full lab\n'
    printf '  6. Custom\n\n'
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
    printf 'Current saved profile:\n'
    guided_print_profile_summary
    echo
    ask choice "Select profile:"
    case "$choice" in
        1) profile=ssc_only ;;
        2) profile=sast_standalone ;;
        3) profile=sast_full ;;
        4) profile=dast_full ;;
        5|"") profile=full_lab ;;
        6) fortify_lab_show_action_warning vulnerable-sample; profile=sample_apps ;;
        7) guided_custom_component_prompt; return $? ;;
        *) error "Invalid profile selection"; sleep 1; return 1 ;;
    esac
    guided_apply_deployment_profile "$profile"
    printf '\nExpanded deployment plan:\n'
    guided_print_profile_summary
    if confirm "Save this profile to .env?"; then
        guided_profile_save "$profile"
    else
        note "Using this profile for the current wizard session only."
    fi
}

guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"

# Guided lifecycle states: pending -> running -> verifying -> complete/failed/skipped.
guided_step_index() {
    local wanted="$1" idx
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        [ "${GUIDED_STEP_ID[$idx]}" = "$wanted" ] && { printf '%s\n' "$idx"; return 0; }
    done
    return 1
}

guided_step_probe() {
    local idx
    idx=$(guided_step_index "$1") || return 1
    printf '%s\n' "${GUIDED_STEP_PROBE[$idx]:-}"
}

guided_step_timeout() {
    local idx
    idx=$(guided_step_index "$1") || return 1
    printf '%s\n' "${GUIDED_STEP_TIMEOUT[$idx]:-300}"
}

guided_step_is_optional() {
    local idx
    idx=$(guided_step_index "$1") || return 1
    [ "${GUIDED_STEP_OPTIONAL[$idx]:-0}" -eq 1 ]
}

guided_step_is_manual() {
    local idx
    idx=$(guided_step_index "$1") || return 1
    [ "${GUIDED_STEP_MANUAL[$idx]:-0}" -eq 1 ]
}

guided_step_help_topic() {
    help_guided_topic "$1"
}

guided_mode_context_text() {
    case "${1:-${GUIDED_MODE_CONTEXT:-}}" in
        fresh)
            printf '%s\n' "Guided mode: fresh deployment. The wizard runs a read-only preflight, refuses existing managed releases, and advances only after each probe verifies."
            ;;
        resume)
            printf '%s\n' "Guided mode: resume or repair. Live files and Kubernetes resources choose the first incomplete required step; completed steps remain repairable."
            ;;
        component)
            printf '%s\n' "Guided mode: component repair. Expert component actions may run with existing managed releases, while preflight checks remain read-only."
            ;;
        auto)
            printf '%s\n' "Guided mode: auto-advance. Verified non-manual steps continue automatically after the countdown; press i to take control."
            ;;
        *)
            printf '%s\n' "Guided mode: live-derived deployment orchestration."
            ;;
    esac
}

guided_step_action_profile() {
    local idx
    idx=$(guided_step_index "$1") || return 1
    if guided_step_is_manual "$1"; then
        printf 'manual operator action; %s\n' "${GUIDED_STEP_IMPACT[$idx]}"
    elif [ "${GUIDED_STEP_IMPACT[$idx]}" = "read-only" ]; then
        printf '%s\n' "read-only verification"
    else
        printf 'idempotent operation; %s\n' "${GUIDED_STEP_IMPACT[$idx]}"
    fi
}

guided_preflight_contract() {
    case "$1" in
        fresh)
            printf '%s\n' "fresh: read-only preflight plus empty managed-release guard before deployment"
            ;;
        resume)
            printf '%s\n' "resume: read-only preflight; existing managed releases are expected and live state selects the first gap"
            ;;
        component)
            printf '%s\n' "component: read-only preflight; existing managed releases are allowed for expert start/upgrade repair"
            ;;
        *)
            error "Unknown guided preflight mode: $1"
            return 1
            ;;
    esac
}

guided_repair_recommendation() {
    case "$1" in
        prereqs) printf '%s\n' "Repair recommendation: install or refresh host prerequisites, then retry the prerequisite probe. Retry safety: host-package changes only." ;;
        inputs) printf '%s\n' "Repair recommendation: review .env and the Fortify license, then rerun configuration validation. Retry safety: read-only until you choose an edit/import action." ;;
        preflight) printf '%s\n' "Repair recommendation: fix the reported prerequisite, storage, registry, capacity, or required setting before deploying. Retry safety: read-only." ;;
        certs) printf '%s\n' "Repair recommendation: regenerate TLS material only on a fresh lab or before recreating Secrets. Data risk: certificate and key rotation can invalidate existing trust." ;;
        dashboard) printf '%s\n' "Repair recommendation: rerun the idempotent Dashboard deployment and verify the ingress and service accounts. Retry safety: idempotent Kubernetes apply." ;;
        secrets) printf '%s\n' "Repair recommendation: rerun scripts/create-secrets.sh after confirming the license, TLS files, and registry credentials. Data risk: rotating SSC secret.key can invalidate encrypted SSC data." ;;
        mysql) printf '%s\n' "Repair recommendation: retry MySQL start/upgrade and wait for the StatefulSet plus authenticated query. Retry safety: Helm upgrade preserves PVC data." ;;
        postgresql) printf '%s\n' "Repair recommendation: retry PostgreSQL start/upgrade and wait for the StatefulSet plus authenticated query. Retry safety: Helm upgrade preserves PVC data." ;;
        ssc) printf '%s\n' "Repair recommendation: repair MySQL first, then retry SSC and verify service, ingress, and HTTP health. For HTTP 5xx, inspect pod logs locally for migration or database errors." ;;
        lim) printf '%s\n' "Repair recommendation: retry LIM and verify its service, ingress, and HTTP endpoint before DAST. Retry safety: idempotent Kubernetes apply." ;;
        sast_controller) printf '%s\n' "Repair recommendation: verify SAST controller DNS/TLS and chart values, then retry the controller. It does not require SSC unless you are running the integrated SAST profile." ;;
        sast_sensor|sast) printf '%s\n' "Repair recommendation: confirm the SAST controller is healthy and the worker can resolve its controller URL, then retry the sensor. Keep tokens out of logs and command output." ;;
        dast_core) printf '%s\n' "Repair recommendation: confirm PostgreSQL, SSC, and LIM are healthy, then retry DAST Core. Preserve database PVCs while troubleshooting." ;;
        dast_scanner|dast) printf '%s\n' "Repair recommendation: confirm DAST Core is healthy, then retry the DAST scanner. Preserve database PVCs while troubleshooting." ;;
        configure) printf '%s\n' "Repair recommendation: complete DNS, SSC ControllerToken, and LIM pool actions from the Configure menu. Retry safety: manual operator action." ;;
        *) printf '%s\n' "Repair recommendation: inspect the failing probe detail, fix the underlying resource, then retry. Avoid destructive cleanup unless a step explicitly says data will be deleted." ;;
    esac
}

prereqs_complete() {
    local command
    for command in openssl envsubst curl; do
        command -v "$command" >/dev/null 2>&1 || return 1
    done
    java_ready && docker_ready && mkcert_ready && microk8s_access_ready || return 1
    return 0
}

inputs_complete() {
    [ -s "$ENV_FILE" ] || return 1
    env_config_valid || return 1
    ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
      fortify_resolve_license_file ) >/dev/null 2>&1
}

deployment_inputs_menu() {
    while true; do
        title "Configuration and license"
        printf '\n  .env:    %s\n' "$ENV_FILE"
        printf '  License: %s\n\n' "$(status_license)"
        echo "  1. Configuration editor"
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
    local variable
    prereqs_complete && inputs_complete && cluster_reachable || return 1
    microk8s status >/dev/null 2>&1 || return 1
    $KUBECTL get storageclass nfs >/dev/null 2>&1 || return 1
    [ -s "$HOME/.docker/config.json" ] || return 1
    for variable in DOMAIN NAMESPACE DEFAULT_PASS FORTIFY_SSC_CHART_VERSION \
        FORTIFY_SSC_IMAGE_TAG FORTIFY_SCSAST_CHART_VERSION; do
        [ -n "${!variable:-}" ] || return 1
    done
    return 0
}

lab_node_ip() {
    hostname -I 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i !~ /^127\./) { print $i; exit } }'
}

lab_hostnames() {
    printf '%s\n' "ssc.$DOMAIN" "sast.$DOMAIN" "dast.$DOMAIN" "lim.$DOMAIN" "dashboard.$DOMAIN"
}

lab_hosts_resolution_detail() {
    local host resolved loopback_hosts wrong_ip_hosts node_ip
    node_ip=$(lab_node_ip)
    while IFS= read -r host; do
        [ -n "$host" ] || continue
        resolved=$(getent ahostsv4 "$host" 2>/dev/null | awk 'NR==1 {print $1}')
        if [ -z "$resolved" ]; then
            printf 'Hostname %s does not resolve on this machine; add it to client DNS or /etc/hosts.\n' "$host"
            return 0
        fi
        if [[ "$resolved" == 127.* ]]; then
            loopback_hosts="${loopback_hosts:+$loopback_hosts, }$host=$resolved"
        elif [ -n "$node_ip" ] && [ "$resolved" != "$node_ip" ]; then
            wrong_ip_hosts="${wrong_ip_hosts:+$wrong_ip_hosts, }$host=$resolved"
        fi
    done < <(lab_hostnames)
    if [ -n "${loopback_hosts:-}" ]; then
        printf 'Lab hostnames resolve to loopback (%s). Map them to the lab node IP%s instead.\n' "$loopback_hosts" "${node_ip:+, for example $node_ip}"
        return 0
    fi
    if [ -n "${wrong_ip_hosts:-}" ]; then
        printf 'Lab hostnames resolve to %s, but this lab node appears to be %s. If that address is Traefik or another proxy, the browser may show TRAEFIK DEFAULT CERT and a 404.\n' "$wrong_ip_hosts" "${node_ip:-unknown}"
        return 0
    fi
    printf 'Lab hostnames resolve to the lab node IP for client access.\n'
}

certs_ready() {
    [ -s "$SERVER_CERT" ] && [ -s "$SERVER_KEY" ] &&
        [ -s "$JVM_KEYSTORE" ] && [ -s "$TRUSTSTORE" ] || return 1
    openssl x509 -in "$SERVER_CERT" -noout >/dev/null 2>&1 || return 1
    openssl rsa -in "$SERVER_KEY" -check -noout >/dev/null 2>&1 || return 1
    keytool -list -keystore "$JVM_KEYSTORE" -storepass "$DEFAULT_PASS" >/dev/null 2>&1 || return 1
    keytool -list -keystore "$TRUSTSTORE" -storepass "$DEFAULT_PASS" >/dev/null 2>&1 || return 1
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

statefulset_in_progress() {
    local namespace="$1" name="$2" desired ready
    cluster_reachable || return 1
    desired=$($KUBECTL -n "$namespace" get statefulset "$name" -o jsonpath='{.spec.replicas}' 2>/dev/null) || return 1
    [ "${desired:-0}" -gt 0 ] || return 1
    ready=$($KUBECTL -n "$namespace" get statefulset "$name" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || printf '0')
    [ "${ready:-0}" -lt "$desired" ]
}

pod_status_lines() {
    local now
    cluster_reachable || return 1
    now="$SECONDS"
    if [ "${GUIDED_POD_STATUS_CACHE_SECONDS:-}" != "$now" ]; then
        GUIDED_POD_STATUS_CACHE=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null || true)
        GUIDED_POD_STATUS_CACHE_SECONDS="$now"
    fi
    printf '%s\n' "$GUIDED_POD_STATUS_CACHE"
}

pod_prefix_in_progress() {
    local prefix="$1"
    cluster_reachable || return 1
    pod_status_lines | awk -v p="$prefix" '
            $1 ~ "^" p {
                found=1
                n=split($2,a,"/")
                if ($3!="Running" || a[1] != a[2]) progress=1
            }
            END { exit found && progress ? 0 : 1 }
        '
}

sast_pods_ready() {
    pod_prefix_ready scancentral-sast
}

sast_pods_in_progress() {
    pod_prefix_in_progress scancentral-sast
}

pod_prefix_ready() {
    local prefix="$1" pods total ready
    cluster_reachable || return 1
    pods=$(pod_status_lines | awk -v p="$prefix" '$1 ~ "^"p {print}')
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

secrets_required_secret_names() {
    printf '%s\n' \
        regcred fortify-secrets tls tls-pfx tls-pfx-password \
        scdast-utilityservice-certificate scdast-db-owner scdast-db-standard \
        scdast-ssc-serviceaccount scdast-service-token lim-pool \
        lim-admin-credentials lim-jwt-security-key lim-server-certificate \
        lim-signing-certificate lim-signing-certificate-password
}

secrets_required_fortify_keys() {
    printf '%s\n' \
        fortify.license ssc.autoconfig secret.key keystore.jks truststore \
        default_password scancentral-client-auth-token \
        scancentral-worker-auth-token scancentral-ssc-scancentral-ctrl-secret \
        jvm_truststore http_truststore keystore_password key_password \
        jvm_truststore_password http_truststore_password keystore_alias
}

secret_key_exists() {
    local secret="$1" key="$2"
    cluster_reachable || return 1
    $KUBECTL -n "$NAMESPACE" get secret "$secret" \
        -o "go-template={{ index .data \"$key\" }}" 2>/dev/null | grep -q .
}

secrets_missing_detail() {
    local required_secret required_key
    cluster_reachable || {
        printf '%s\n' "Cluster is not reachable while checking Kubernetes Secrets."
        return 0
    }
    for required_secret in $(secrets_required_secret_names); do
        if ! resource_exists "$NAMESPACE" secret "$required_secret"; then
            printf 'Missing secret %s in namespace %s.\n' "$required_secret" "$NAMESPACE"
            return 0
        fi
    done
    for required_key in $(secrets_required_fortify_keys); do
        if ! secret_key_exists fortify-secrets "$required_key"; then
            printf 'Missing key %s in secret fortify-secrets.\n' "$required_key"
            return 0
        fi
    done
    printf '%s\n' "All required Kubernetes Secrets and fortify-secrets keys are present."
}

secrets_ready() {
    local required_secret required_key
    for required_secret in $(secrets_required_secret_names); do
        resource_exists "$NAMESPACE" secret "$required_secret" || return 1
    done
    for required_key in $(secrets_required_fortify_keys); do
        secret_key_exists fortify-secrets "$required_key" || return 1
    done
}

mysql_ready() {
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    health_mysql_statefulset_probe && health_mysql_query
}

postgresql_ready() {
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    health_postgresql_statefulset_probe && health_postgresql_query
}

ssc_ready() {
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    health_ssc_statefulset_probe && health_ssc_service_probe &&
        health_ssc_ingress_probe && health_ssc_http_probe
}

lim_ready() {
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    health_lim_statefulset_probe && health_lim_service_probe &&
        health_lim_ingress_probe && health_lim_http_probe
}

sast_controller_ready() {
    workload_ready "$NAMESPACE" statefulset scancentral-sast-controller
}

sast_sensor_ready() {
    sast_controller_ready && workload_ready "$NAMESPACE" statefulset scancentral-sast-worker-linux
}

sast_ready() {
    sast_sensor_ready
}

dast_core_ready() {
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    health_dast_core_workloads_probe && health_dast_http_probe
}

dast_scanner_ready() {
    dast_core_ready && workload_ready "$NAMESPACE" statefulset sdast-scanner-scancentral-dast-scanner
}

dast_ready() {
    dast_scanner_ready
}

sample_juice_shop_ready() {
    workload_ready "$NAMESPACE" deployment sample-juice-shop && resource_exists "$NAMESPACE" service sample-juice-shop && resource_exists "$NAMESPACE" ingress sample-juice-shop
}

sample_webgoat_ready() {
    workload_ready "$NAMESPACE" deployment sample-webgoat && resource_exists "$NAMESPACE" service sample-webgoat && resource_exists "$NAMESPACE" ingress sample-webgoat
}

sample_dvwa_ready() {
    workload_ready "$NAMESPACE" deployment sample-dvwa && resource_exists "$NAMESPACE" service sample-dvwa && resource_exists "$NAMESPACE" ingress sample-dvwa
}

configure_ready() {
    return 1
}

guided_step_complete() {
    local probe
    probe=$(guided_step_probe "$1") || return 1
    [ -n "$probe" ] || return 1
    "$probe"
}

guided_step_live_complete() {
    case "$1" in
        mysql) pod_prefix_ready mysql ;;
        postgresql) pod_prefix_ready postgresql ;;
        ssc) pod_prefix_ready ssc-webapp ;;
        lim) pod_prefix_ready lim ;;
        sast_controller) pod_prefix_ready scancentral-sast-controller ;;
        sast_sensor|sast) pod_prefix_ready scancentral-sast ;;
        dast_core) pod_prefix_ready sdast-core ;;
        dast_scanner|dast) pod_prefix_ready sdast ;;
        *) guided_step_complete "$1" ;;
    esac
}

guided_step_live_in_progress() {
    case "$1" in
        mysql) pod_prefix_in_progress mysql ;;
        postgresql) pod_prefix_in_progress postgresql ;;
        ssc) pod_prefix_in_progress ssc-webapp ;;
        lim) pod_prefix_in_progress lim ;;
        sast_controller) pod_prefix_in_progress scancentral-sast-controller ;;
        sast_sensor|sast) pod_prefix_in_progress scancentral-sast ;;
        dast_core) pod_prefix_in_progress sdast-core ;;
        dast_scanner|dast) pod_prefix_in_progress sdast ;;
        *) guided_step_in_progress "$1" ;;
    esac
}

guided_step_live_status() {
    if guided_step_live_complete "$1"; then
        printf '%scomplete%s' "$GREEN" "$RESET"
    elif guided_step_live_in_progress "$1"; then
        printf '%sin progress%s' "$YELLOW" "$RESET"
    elif guided_step_is_manual "$1"; then
        printf '%smanual%s' "$DIM" "$RESET"
    else
        printf '%spending%s' "$YELLOW" "$RESET"
    fi
}

guided_status_render() {
    case "$1" in
        complete) printf '%scomplete%s' "$GREEN" "$RESET" ;;
        in_progress) printf '%sin progress%s' "$YELLOW" "$RESET" ;;
        manual) printf '%smanual%s' "$DIM" "$RESET" ;;
        *) printf '%spending%s' "$YELLOW" "$RESET" ;;
    esac
}

guided_step_live_state() {
    if guided_step_live_complete "$1"; then
        printf '%s\n' complete
    elif guided_step_live_in_progress "$1"; then
        printf '%s\n' in_progress
    elif guided_step_is_manual "$1"; then
        printf '%s\n' manual
    else
        printf '%s\n' pending
    fi
}

guided_collect_step_statuses() {
    local idx id state total="${#GUIDED_STEP_ID[@]}" row
    GUIDED_STEP_STATUS_CACHE=()
    GUIDED_STEP_COMPLETE_CACHE=()
    section "Checking deployment state"
    printf '  Deriving live state from files and Kubernetes.\n\n'
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        id="${GUIDED_STEP_ID[$idx]}"
        row=$(printf '  [%2d/%2d] %-30s' "$((idx + 1))" "$total" "${GUIDED_STEP_LABEL[$idx]}")
        if [ -t 1 ]; then
            printf '%s %s' "$row" "checking..."
        fi
        state=$(guided_step_live_state "$id")
        GUIDED_STEP_STATUS_CACHE[$idx]="$state"
        case "$state" in
            complete) GUIDED_STEP_COMPLETE_CACHE[$idx]=1 ;;
            *) GUIDED_STEP_COMPLETE_CACHE[$idx]=0 ;;
        esac
        if [ -t 1 ]; then
            printf '\r%s %s\033[K\n' "$row" "$(guided_status_render "$state")"
        else
            printf '%s %s\n' "$row" "$(guided_status_render "$state")"
        fi
    done
}
guided_cached_step_status() {
    local idx="$1" state
    state="${GUIDED_STEP_STATUS_CACHE[$idx]:-}"
    if [ -z "$state" ]; then
        state=$(guided_step_live_state "${GUIDED_STEP_ID[$idx]}")
    fi
    guided_status_render "$state"
}

guided_cached_step_complete() {
    local idx="$1"
    if [ -n "${GUIDED_STEP_COMPLETE_CACHE[$idx]+set}" ]; then
        [ "${GUIDED_STEP_COMPLETE_CACHE[$idx]}" -eq 1 ]
        return
    fi
    guided_step_live_complete "${GUIDED_STEP_ID[$idx]}"
}

guided_step_in_progress() {
    case "$1" in
        dashboard)
            resource_exists "$(dashboard_access_namespace)" ingress ingress-dashboard &&
                ! dashboard_ready
            ;;
        mysql) statefulset_in_progress "$NAMESPACE" mysql ;;
        postgresql) statefulset_in_progress "$NAMESPACE" postgresql ;;
        ssc) statefulset_in_progress "$NAMESPACE" ssc-webapp ;;
        lim) statefulset_in_progress "$NAMESPACE" lim ;;
        sast_controller) statefulset_in_progress "$NAMESPACE" scancentral-sast-controller ;;
        sast_sensor|sast) sast_pods_in_progress ;;
        dast_core)
            statefulset_in_progress "$NAMESPACE" sdast-core-scancentral-dast-core-api ||
                statefulset_in_progress "$NAMESPACE" sdast-core-scancentral-dast-core-globalservice ||
                statefulset_in_progress "$NAMESPACE" sdast-core-scancentral-dast-core-utilityservice
            ;;
        dast_scanner) statefulset_in_progress "$NAMESPACE" sdast-scanner-scancentral-dast-scanner ;;
        dast)
            statefulset_in_progress "$NAMESPACE" sdast-core-scancentral-dast-core-api ||
                statefulset_in_progress "$NAMESPACE" sdast-core-scancentral-dast-core-globalservice ||
                statefulset_in_progress "$NAMESPACE" sdast-core-scancentral-dast-core-utilityservice ||
                statefulset_in_progress "$NAMESPACE" sdast-scanner-scancentral-dast-scanner
            ;;
        *) return 1 ;;
    esac
}

guided_step_status() {
    if guided_step_complete "$1"; then
        printf '%scomplete%s' "$GREEN" "$RESET"
    elif guided_step_in_progress "$1"; then
        printf '%sin progress%s' "$YELLOW" "$RESET"
    elif guided_step_is_manual "$1"; then
        printf '%smanual%s' "$DIM" "$RESET"
    else
        printf '%spending%s' "$YELLOW" "$RESET"
    fi
}

guided_component_endpoint_detail() {
    local service="$1" ingress="$2" host="$3" url="$4"
    source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
    if ! health_service_endpoints_ready "$service"; then
        printf 'Service %s has no ready endpoints yet.\n' "$service"
    elif ! health_ingress_host_ready "$ingress" "$host"; then
        printf 'Ingress %s does not contain host %s yet.\n' "$ingress" "$host"
    else
        FORTIFY_HEALTH_HTTP_MAX_TIME=3 health_http_detail "$url"
    fi
}

guided_step_progress_message() {
    case "$1" in
        prereqs) printf '%s\n' "Checking host tools and MicroK8s add-ons." ;;
        inputs) printf '%s\n' "Waiting for .env and a readable Fortify license." ;;
        preflight) printf '%s\n' "Validating cluster reachability, storage, registry login, capacity, and required settings." ;;
        certs) printf '%s\n' "Checking TLS certificate, private key, JVM keystore, and truststore artifacts." ;;
        dashboard) printf '%s\n' "Waiting for Dashboard workloads, service, ingress, and TLS material." ;;
        secrets) secrets_missing_detail ;;
        mysql) printf '%s\n' "Waiting for the MySQL StatefulSet and an authenticated query." ;;
        postgresql) printf '%s\n' "Waiting for the PostgreSQL StatefulSet and an authenticated query." ;;
        ssc) guided_component_endpoint_detail ssc-service ssc-ingress "${SSC:?SSC is required}" "${SSC_URL:?SSC_URL is required}" ;;
        lim) guided_component_endpoint_detail lim lim-ingress "${LIM:?LIM is required}" "${LIM_URL:?LIM_URL is required}" ;;
        sast_controller) printf '%s\n' "Waiting for the SAST controller StatefulSet." ;;
        sast_sensor|sast) printf '%s\n' "Waiting for the SAST sensor after the controller is ready." ;;
        dast_core)
            source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
            FORTIFY_HEALTH_HTTP_MAX_TIME=3 health_http_detail "${SCDAST_URL:?SCDAST_URL is required}"
            ;;
        dast_scanner|dast) printf '%s\n' "Waiting for the DAST scanner after DAST Core is ready." ;;
        configure) lab_hosts_resolution_detail ;;
        *) printf '%s\n' "Unknown guided step." ;;
    esac
}

guided_step_why_pending() {
    local id="$1"
    if guided_step_complete "$id"; then
        printf '%s\n' "Step is complete; no pending action is required."
    elif guided_step_in_progress "$id"; then
        printf '%s\n' "Step is in progress; continue watching verification before retrying."
    else
        guided_step_progress_message "$id"
    fi
}

guided_step_pod_prefixes() {
    case "$1" in
        mysql) printf '%s\n' mysql ;;
        postgresql) printf '%s\n' postgresql ;;
        ssc) printf '%s\n' ssc-webapp ;;
        lim) printf '%s\n' lim ;;
        sast_controller) printf '%s\n' scancentral-sast-controller ;;
        sast_sensor|sast) printf '%s\n' scancentral-sast ;;
        dast_core) printf '%s\n' sdast-core ;;
        dast_scanner|dast) printf '%s\n' sdast ;;
    esac
}

guided_step_has_pod_logs() {
    [ -n "$(guided_step_pod_prefixes "$1")" ]
}

guided_step_services() {
    case "$1" in
        ssc) printf '%s\n' ssc-service ;;
        lim) printf '%s\n' lim ;;
        sast_controller|sast_sensor|sast) printf '%s\n' scancentral-sast-controller ;;
        dast_core|dast_scanner|dast) printf '%s\n' sdast-core-scancentral-dast-core-api ;;
    esac
}

guided_step_hosts() {
    case "$1" in
        ssc) printf '%s\n' "${SSC:-}" ;;
        lim) printf '%s\n' "${LIM:-}" ;;
        sast_controller|sast_sensor|sast) printf '%s\n' "${SCSAST:-}" ;;
        dast_core|dast_scanner|dast) printf '%s\n' "${SCDAST:-}" ;;
        dashboard) printf '%s\n' "dashboard.${DOMAIN:-fortifydemo.com}" ;;
    esac
}

guided_print_pods() {
    local id="$1" prefix pods
    cluster_reachable || { printf '  Cluster unavailable for pod status.\n'; return 0; }
    prefix=$(guided_step_pod_prefixes "$id")
    [ -n "$prefix" ] || { printf '  No pod status applies to this step yet.\n'; return 0; }
    pods=$(pod_status_lines | awk -v p="$prefix" '$1 ~ "^"p {print}')
    if [ -z "$pods" ]; then
        printf '  No pods matching %s have appeared yet.\n' "$prefix"
    else
        echo "$pods" | awk '{ printf "  %-56s %-8s %s\n", $1, $2, $3 }'
    fi
}

guided_print_recent_events() {
    cluster_reachable || return 0
    $KUBECTL -n "$NAMESPACE" get events --sort-by='.lastTimestamp' 2>/dev/null \
        | tail -5 | awk 'NR>0 { printf "  %s\n", $0 }'
}


guided_print_step_events() {
    local id="$1" prefix
    cluster_reachable || return 0
    prefix=$(guided_step_pod_prefixes "$id")
    if [ -z "$prefix" ]; then
        guided_print_recent_events
        return 0
    fi
    $KUBECTL -n "$NAMESPACE" get events --sort-by='.lastTimestamp' 2>/dev/null \
        | awk -v p="$prefix" 'NR == 1 || index($0, p) { lines[++count] = $0 } END { start = count - 4; if (start < 1) start = 1; for (i = start; i <= count; i++) printf "  %s\n", lines[i] }'
}

guided_print_step_services() {
    local id="$1" service any=0
    cluster_reachable || { printf '  Cluster unavailable for service status.\n'; return 0; }
    while IFS= read -r service; do
        [ -n "$service" ] || continue
        any=1
        if $KUBECTL -n "$NAMESPACE" get service "$service" >/dev/null 2>&1; then
            $KUBECTL -n "$NAMESPACE" get service "$service" \
                -o 'custom-columns=NAME:.metadata.name,TYPE:.spec.type,PORTS:.spec.ports[*].port' 2>/dev/null \
                | sed 's/^/  /'
        else
            printf '  %s service is not present yet.\n' "$service"
        fi
        if $KUBECTL -n "$NAMESPACE" get endpoints "$service" >/dev/null 2>&1; then
            $KUBECTL -n "$NAMESPACE" get endpoints "$service" \
                -o 'custom-columns=NAME:.metadata.name,ENDPOINTS:.subsets[*].addresses[*].ip,PORTS:.subsets[*].ports[*].port' 2>/dev/null \
                | sed 's/^/  /'
        fi
    done < <(guided_step_services "$id")
    [ "$any" -eq 1 ] || printf '  No service endpoint check applies to this step yet.\n'
}

guided_print_step_ingresses() {
    local id="$1" host any=0 matches
    cluster_reachable || { printf '  Cluster unavailable for ingress status.\n'; return 0; }
    while IFS= read -r host; do
        [ -n "$host" ] || continue
        any=1
        matches=$($KUBECTL -n "$NAMESPACE" get ingress \
            -o 'custom-columns=NAME:.metadata.name,CLASS:.spec.ingressClassName,HOSTS:.spec.rules[*].host,ADDRESS:.status.loadBalancer.ingress[*].ip' 2>/dev/null \
            | awk -v h="$host" 'NR == 1 { header=$0; next } index($0, h) { if (!printed) { print header; printed=1 } print; found=1 } END { exit found ? 0 : 1 }') || matches=""
        if [ -n "$matches" ]; then
            printf '%s\n' "$matches" | sed 's/^/  /'
        else
            printf '  No ingress currently matches %s.\n' "$host"
        fi
    done < <(guided_step_hosts "$id")
    [ "$any" -eq 1 ] || printf '  No ingress check applies to this step yet.\n'
}

guided_live_diagnostics() {
    local id="$1" label="${2:-$1}"
    section "Live diagnostics for $label"
    printf '  Status: %s\n' "$(guided_step_live_status "$id")"
    printf '  Detail: %s\n' "$(guided_step_why_pending "$id")"
    section "Pods"
    guided_print_pods "$id"
    section "Services and endpoints"
    guided_print_step_services "$id"
    section "Ingress"
    guided_print_step_ingresses "$id"
    section "Recent matching events"
    guided_print_step_events "$id"
}

guided_step_pod_logs() {
    local id="$1" label="${2:-$1}" prefix pods
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any
        return 1
    fi
    prefix=$(guided_step_pod_prefixes "$id")
    if [ -z "$prefix" ]; then
        note "No pod logs apply to $label yet."
        press_any
        return 1
    fi
    mapfile -t pods < <(k8s_resource_names pod "" "$prefix")
    if [ ${#pods[@]} -eq 0 ]; then
        note "No pods matching '$prefix' have appeared yet. Recent events may explain what is still pending."
        section "Recent events"
        guided_print_recent_events
        press_any
        return 1
    fi
    if [ ${#pods[@]} -eq 1 ]; then
        pod_log_action_menu "${pods[0]}"
        return $?
    fi
    if k8s_select_resource pod "Select a pod for $label" "" "$prefix"; then
        pod_log_action_menu "$K8S_SELECTED_RESOURCE_NAME"
    fi
}

guided_diagnostics_bundle() {
    local output_dir bundle
    output_dir="${XDG_STATE_HOME:-$HOME/.local/state}/fortify-lab/diagnostics"
    if ! mkdir -p -- "$output_dir" || ! chmod 700 -- "$output_dir"; then
        error "Could not create the private diagnostics output directory."
        return 1
    fi
    if bundle=$(operational_create_diagnostics_bundle "$output_dir"); then
        note "Sanitized bundle created: $bundle"
        note "Review it before sharing; no automated sanitizer can prove all context is safe."
    else
        error "Diagnostics bundle creation failed."
        return 1
    fi
}

wizard_log_event() {
    fortify_wizard_log INFO "$@" >/dev/null 2>&1 || true
}

wizard_log_viewer() {
    local lines="${FORTIFY_WIZARD_LOG_VIEW_LINES:-120}" log_file
    title "Wizard log"
    log_file=$(fortify_wizard_log_file 2>/dev/null || true)
    if [ -n "$log_file" ]; then
        printf '\n  Log file: %s\n' "$log_file"
    fi
    printf '  Showing the last %s sanitized lines. Review before sharing.\n\n' "$lines"
    if ! fortify_wizard_log_view "$lines" 2>/dev/null | sed 's/^/  /'; then
        error "Could not read the wizard log."
    fi
    press_any
}

GUIDED_WAIT_SCREEN_LINES=0
GUIDED_WAIT_SCREEN_ACTIVE=0

guided_wait_screen_tty() {
    [ -t 1 ] && [ "${FORTIFY_GUIDED_WAIT_ALT_SCREEN:-1}" != 0 ]
}

guided_wait_screen_enter() {
    GUIDED_WAIT_SCREEN_LINES=0
    GUIDED_WAIT_SCREEN_ACTIVE=0
    guided_wait_screen_tty || return 0
    # Use the terminal alternate screen for live verification dashboards so
    # repeated refreshes do not push older frames into scrollback.
    printf '\033[?1049h\033[?25l\033[H\033[J'
    GUIDED_WAIT_SCREEN_ACTIVE=1
}

guided_wait_screen_render_start() {
    if guided_wait_screen_tty; then
        printf '\033[H\033[J'
    else
        printf '\n'
    fi
}

guided_wait_screen_render_finish() {
    GUIDED_WAIT_SCREEN_LINES="${1:-0}"
}

guided_wait_screen_line() {
    printf '\033[K%s\n' "$*"
}

guided_wait_screen_leave() {
    [ "${GUIDED_WAIT_SCREEN_ACTIVE:-0}" -eq 1 ] || return 0
    printf '\033[?25h\033[?1049l'
    GUIDED_WAIT_SCREEN_ACTIVE=0
    GUIDED_WAIT_SCREEN_LINES=0
}

guided_wait_render() {
    local id="$1" label="$2" elapsed="$3" remaining="$4" interval="$5" timeout="$6" probe="$7"
    printf '\n%s%s%s\n' "$BOLD" "Verifying $label" "$RESET"
    hr
    printf '\n  State:   %s\n' "$(guided_step_live_status "$id")"
    printf '  Probe:   %s\n' "$probe"
    printf '  Elapsed: %ss' "$elapsed"
    [ "$timeout" -gt 0 ] && printf ' / %ss' "$timeout"
    printf '\n  Detail:  %s\n\n' "$(guided_step_progress_message "$id")"
    section "Pods"
    guided_print_pods "$id"
    section "Recent events"
    guided_print_recent_events
    printf '\n  r. Retry operation   i. Take interactive control   p. Pod logs   l. Wizard log   h. Help\n'
    printf '  d. Live diagnostics   x. Export diagnostics bundle   q. Quit safely\n'
    printf '  Waiting %ss before the next refresh' "$interval"
    [ "$timeout" -gt 0 ] && printf ' (%ss remaining)' "$remaining"
    printf '...\n'
}

guided_wait_screen_render() {
    local content line rendered_lines=0
    content=$(guided_wait_render "$@")
    guided_wait_screen_render_start
    if [ -t 1 ]; then
        while IFS= read -r line || [ -n "$line" ]; do
            guided_wait_screen_line "$line"
            rendered_lines=$((rendered_lines + 1))
        done <<< "$content"
        guided_wait_screen_render_finish "$rendered_lines"
    else
        printf '%s\n' "$content"
    fi
}

guided_wait_for_step() {
    local id="$1" label="$2" timeout interval started elapsed remaining control topic probe
    timeout=$(guided_step_timeout "$id") || timeout=300
    interval="${GUIDED_WAIT_INTERVAL:-5}"
    [[ "$timeout" =~ ^[0-9]+$ ]] || timeout=300
    [[ "$interval" =~ ^[1-9][0-9]*$ ]] || interval=5
    GUIDED_WAIT_LAST_FAILURE=""
    GUIDED_WAIT_LAST_STATE="verifying"
    probe=$(guided_step_probe "$id") || probe="unknown"
    wizard_log_event "action=verification_start step=$id probe=$probe timeout=$timeout"

    if guided_step_is_manual "$id"; then
        GUIDED_WAIT_LAST_STATE="manual"
        note "$label needs operator action; automatic verification is not available."
        return 0
    fi

    guided_wait_screen_enter

    started=$SECONDS
    while true; do
        if guided_step_complete "$id"; then
            GUIDED_WAIT_LAST_STATE="complete"
            guided_wait_screen_leave
            wizard_log_event "action=verification_finish step=$id probe=$probe state=complete elapsed=$((SECONDS - started))"
            note "$label verified ready."
            return 0
        fi

        elapsed=$((SECONDS - started))
        if [ "$timeout" -gt 0 ] && [ "$elapsed" -ge "$timeout" ]; then
            GUIDED_WAIT_LAST_STATE="failed"
            GUIDED_WAIT_LAST_FAILURE="$label did not verify ready within ${timeout}s; probe $probe is still failing."
            error "$GUIDED_WAIT_LAST_FAILURE"
            guided_wait_screen_leave
            wizard_log_event "action=verification_finish step=$id probe=$probe state=failed elapsed=$elapsed detail=$GUIDED_WAIT_LAST_FAILURE"
            guided_repair_recommendation "$id" >&2
            help_print_topic_reference "$(guided_step_help_topic "$id")"
            return 1
        fi

        remaining=$((timeout - elapsed))
        [ "$timeout" -eq 0 ] && remaining=0
        guided_wait_screen_render "$id" "$label" "$elapsed" "$remaining" "$interval" "$timeout" "$probe"

        if read -rsn1 -t "$interval" control; then
            case "$control" in
                [Rr])
                    GUIDED_WAIT_LAST_STATE="retry"
                    guided_wait_screen_leave
                    note "Retry requested."
                    wizard_log_event "action=user_control step=$id control=retry"
                    return 4
                    ;;
                [Ii])
                    GUIDED_WAIT_LAST_STATE="interactive"
                    guided_wait_screen_leave
                    note "Interactive control requested."
                    wizard_log_event "action=user_control step=$id control=interactive_takeover"
                    return 2
                    ;;
                [Hh]|\?)
                    guided_wait_screen_leave
                    topic=$(guided_step_help_topic "$id") || topic=overview
                    wizard_log_event "action=user_control step=$id control=help"
                    help_show_topic "$topic"
                    guided_wait_screen_enter
                    ;;
                [Pp])
                    guided_wait_screen_leave
                    wizard_log_event "action=user_control step=$id control=pod_logs"
                    guided_step_pod_logs "$id" "$label"
                    guided_wait_screen_enter
                    ;;
                [Ll])
                    guided_wait_screen_leave
                    wizard_log_event "action=user_control step=$id control=view_log"
                    wizard_log_viewer
                    guided_wait_screen_enter
                    ;;
                [Dd])
                    guided_wait_screen_leave
                    wizard_log_event "action=user_control step=$id control=live_diagnostics"
                    guided_live_diagnostics "$id" "$label"
                    press_any
                    guided_wait_screen_enter
                    ;;
                [Xx])
                    guided_wait_screen_leave
                    wizard_log_event "action=user_control step=$id control=diagnostics_bundle"
                    guided_diagnostics_bundle
                    press_any
                    guided_wait_screen_enter
                    ;;
                [Qq])
                    GUIDED_WAIT_LAST_STATE="quit"
                    guided_wait_screen_leave
                    note "No wizard state or secrets were written. Live resources will be detected when you resume."
                    wizard_log_event "action=user_control step=$id control=quit_safely"
                    return 3
                    ;;
            esac
        fi
    done
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
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
    for id in "${GUIDED_STEP_ID[@]}"; do
        case "$id" in prereqs|configure) continue ;; esac
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

wizard_doctor_load_env() {
    if [ -f "$ENV_FILE" ]; then
        # shellcheck disable=SC1090
        source "$ENV_FILE"
    fi
    DOMAIN="${DOMAIN:-fortifydemo.com}"
    NAMESPACE="${NAMESPACE:-fortify}"
    SSC="${SSC:-ssc.$DOMAIN}"
    LIM="${LIM:-lim.$DOMAIN}"
    SCDAST="${SCDAST:-dast.$DOMAIN}"
    SCSAST="${SCSAST:-sast.$DOMAIN}"
    SSC_URL="${SSC_URL:-https://$SSC}"
    LIM_URL="${LIM_URL:-https://$LIM}"
    SCDAST_URL="${SCDAST_URL:-https://$SCDAST}"
    SCSAST_CTRL_URL="${SCSAST_CTRL_URL:-https://$SCSAST}"
    FORTIFY_OPERATION_NAMESPACE="$NAMESPACE"
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
}

wizard_config_diagnostics() {
    wizard_doctor_load_env
    env_diagnostics
}

wizard_doctor() {
    local id incomplete=0 unavailable=0
    wizard_doctor_load_env
    wizard_log_event "action=doctor_start mode=doctor"
    operational_cluster_available || unavailable=1
    operational_doctor_compact_health_summary || unavailable=1
    printf '\nDetailed checks:\n'
    operational_doctor_hosts_resolution || true
    operational_doctor_coredns_drift || true
    operational_doctor_ingress || true
    operational_doctor_service_endpoints || true
    operational_doctor_http_status || true
    printf '\nGuided readiness:\n'
    for id in "${GUIDED_STEP_ID[@]}"; do
        if guided_step_complete "$id"; then
            printf '  %-12s complete\n' "$id"
        elif guided_step_in_progress "$id"; then
            printf '  %-12s in-progress - %s\n' "$id" "$(guided_step_why_pending "$id")"
            incomplete=1
        else
            printf '  %-12s needs-attention - %s\n' "$id" "$(guided_step_why_pending "$id")"
            incomplete=1
        fi
    done
    wizard_log_event "action=doctor_finish state=$([ "$incomplete" -eq 0 ] && [ "$unavailable" -eq 0 ] && printf healthy || printf degraded)"
    if [ "$unavailable" -ne 0 ]; then
        return 2
    fi
    [ "$incomplete" -eq 0 ] && return 0
    return 1
}

managed_release_names() {
    [ -n "${HELM:-}" ] && [ -n "${NAMESPACE:-}" ] && cluster_reachable || return 0
    $HELM -n "$NAMESPACE" list -q 2>/dev/null \
        | grep -E '^(mysql|postgresql|ssc|lim|scancentral-sast|sdast-core|sdast-scanner)$' || true
}

managed_releases_exist() {
    [ -n "$(managed_release_names)" ]
}

fresh_deployment_guard() {
    local releases
    releases=$(managed_release_names)
    if [ -n "$releases" ]; then
        error "Managed releases already exist; choose Resume or repair deployment, or Manage individual components -> Start / Upgrade."
        printf '%s\n' "$releases" | awk '{ printf "  existing release: %s\n", $0 }'
        return 1
    fi
}

# This is the sole operation dispatcher for both interactive deployment modes.
# Rendering guided status never calls it.
run_deployment_operation() {
    local operation="$1" rc
    wizard_log_event "action=operation_start step=$operation mode=${GUIDED_MODE_CONTEXT:-unknown}"
    ensure_registry_credentials "$operation" || { rc=$?; wizard_log_event "action=operation_finish step=$operation state=failed exit_code=$rc detail=registry_credentials"; return "$rc"; }
    case "$operation" in
        prereqs) prereqs_menu ;;
        inputs) deployment_inputs_menu ;;
        preflight) preflight_check ;;
        certs) bash "$FORTIFY_HOME_K8S/scripts/create-certs.sh" ;;
        dashboard) bash "$FORTIFY_HOME_K8S/apps/kubernetes-dashboard/deploy.sh" ;;
        secrets) bash "$FORTIFY_HOME_K8S/scripts/create-secrets.sh" ;;
        mysql) run_app_scripts "apps/mysql/start.sh" ;;
        postgresql) run_app_scripts "apps/postgresql/start.sh" ;;
        ssc) deployment_config_guard && run_app_scripts "apps/ssc/start.sh" ;;
        lim) deployment_config_guard && run_app_scripts "apps/lim/start.sh" ;;
        sast_controller) deployment_config_guard && FORTIFY_SCSAST_REQUIRE_SSC=0 FORTIFY_SCSAST_WORKERS_ENABLED=false FORTIFY_SCSAST_WORKER_REPLICAS=0 run_app_scripts "apps/scsast/start.sh" ;;
        sast_sensor) deployment_config_guard && sast_controller_ready && FORTIFY_SCSAST_REQUIRE_SSC=0 FORTIFY_SCSAST_WORKERS_ENABLED=true FORTIFY_SCSAST_WORKER_REPLICAS=1 run_app_scripts "apps/scsast/start.sh" ;;
        sast) deployment_config_guard && FORTIFY_SCSAST_REQUIRE_SSC=0 FORTIFY_SCSAST_WORKERS_ENABLED=true FORTIFY_SCSAST_WORKER_REPLICAS=1 run_app_scripts "apps/scsast/start.sh" ;;
        dast_core) deployment_config_guard && run_app_scripts "apps/scdast/core/start.sh" ;;
        dast_scanner) deployment_config_guard && dast_core_ready && run_app_scripts "apps/scdast/scanner/start.sh" ;;
        dast) deployment_config_guard && run_app_scripts "apps/scdast/core/start.sh apps/scdast/scanner/start.sh" ;;
        sample_juice_shop) fortify_lab_show_action_warning vulnerable-sample && run_app_scripts "apps/samples/juice-shop/start.sh" ;;
        sample_webgoat) fortify_lab_show_action_warning vulnerable-sample && run_app_scripts "apps/samples/webgoat/start.sh" ;;
        sample_dvwa) fortify_lab_show_action_warning vulnerable-sample && run_app_scripts "apps/samples/dvwa/start.sh" ;;
        configure) configure_menu ;;
        *) error "Unknown deployment operation: $operation"; return 1 ;;
    esac
    rc=$?
    wizard_log_event "action=operation_finish step=$operation state=$([ "$rc" -eq 0 ] && printf complete || printf failed) exit_code=$rc"
    return "$rc"
}

guided_run_and_verify() {
    local id="$1" label="$2" result started elapsed
    section "$label"
    started=$SECONDS
    GUIDED_WAIT_LAST_STATE="running"
    wizard_log_event "action=step_enter step=$id label=$label mode=${GUIDED_MODE_CONTEXT:-unknown} profile=$(guided_step_action_profile "$id")"
    if ! run_deployment_operation "$id"; then
        GUIDED_WAIT_LAST_STATE="failed"
        GUIDED_WAIT_LAST_FAILURE="$label operation failed before verification."
        error "$GUIDED_WAIT_LAST_FAILURE"
        error "The step is still incomplete. Correct the issue, then choose Retry."
        guided_repair_recommendation "$id" >&2
        wizard_log_event "action=step_exit step=$id state=failed duration=$((SECONDS - started)) detail=$GUIDED_WAIT_LAST_FAILURE"
        help_print_topic_reference "$(guided_step_help_topic "$id")"
        return 1
    fi
    guided_wait_for_step "$id" "$label"
    result=$?
    elapsed=$((SECONDS - started))
    wizard_log_event "action=step_exit step=$id state=$GUIDED_WAIT_LAST_STATE duration=$elapsed result=$result"
    case "$result" in
        0)
            if guided_step_is_optional "$id" || guided_step_complete "$id"; then
                return 0
            fi
            GUIDED_WAIT_LAST_STATE="failed"
            GUIDED_WAIT_LAST_FAILURE="$label still needs required operator input."
            error "$GUIDED_WAIT_LAST_FAILURE"
            error "The step is still incomplete. Correct the issue, then choose Retry."
            guided_repair_recommendation "$id" >&2
            return 1
            ;;
        2|3|4) return "$result" ;;
        *)
            error "The step is still incomplete. Correct the issue, then choose Retry."
            guided_repair_recommendation "$id" >&2
            return 1
            ;;
    esac
}

guided_countdown() {
    local current_idx="$1" current_label="$2" next_idx="$3" next_label="$4" reason="${5:-verified}"
    local delay="${GUIDED_AUTO_ADVANCE_DELAY:-5}" remaining control total="${#GUIDED_STEP_ID[@]}"
    local current_num next_num
    [[ "$delay" =~ ^[0-9]+$ ]] || delay=5
    current_num=$((current_idx + 1))
    next_num=$((next_idx + 1))
    remaining="$delay"
    while [ "$remaining" -gt 0 ]; do
        printf '\r\033[K  [%d/%d] %s %s. Continuing to [%d/%d] %s in %ss. Press i to stay here.' \
            "$current_num" "$total" "$current_label" "$reason" \
            "$next_num" "$total" "$next_label" "$remaining"
        if read -rsn1 -t 1 control; then
            case "$control" in
                [Ii])
                    printf '\r\033[K'
                    GUIDED_AUTO_ADVANCE=0
                    note "[$next_num/$total] Auto-advance paused: staying interactive at $next_label."
                    return 1
                    ;;
            esac
        fi
        remaining=$((remaining - 1))
    done
    printf '\r\033[K%s [%d/%d] %s %s; continuing to [%d/%d] %s.\n' \
        "$OK_MARK" "$current_num" "$total" "$current_label" "$reason" \
        "$next_num" "$total" "$next_label"
    return 0
}

guided_step_enabled() {
    local wanted="$1"
    guided_step_index "$wanted" >/dev/null 2>&1
}

guided_completion_service_line() {
    local label="$1" url="$2" status="$3"
    printf '    %-22s %-18s %s\n' "$label" "$status" "$url"
}

guided_completion_print_services() {
    if ! cluster_reachable; then
        note "Cluster is not reachable; live service status is unavailable."
        return
    fi
    printf '    %-22s %-18s %s\n' "Service" "Status" "URL"
    printf '    %s\n' "────────────────────────────────────────────────────────────"
    if guided_step_enabled ssc; then
        guided_completion_service_line "SSC" "${SSC_URL:-<unset>}" "$(app_status ssc-webapp)"
    fi
    if guided_step_enabled lim; then
        guided_completion_service_line "LIM" "${LIM_URL:-<unset>}" "$(app_status lim)"
    fi
    if guided_step_enabled sast_controller || guided_step_enabled sast_sensor; then
        guided_completion_service_line "ScanCentral SAST" "${SCSAST_CTRL_URL:-<unset>}" "$(app_status scancentral-sast)"
    fi
    if guided_step_enabled dast_core || guided_step_enabled dast_scanner; then
        guided_completion_service_line "ScanCentral DAST" "${SCDAST_URL:-<unset>}" "$(app_status sdast)"
    fi
    if guided_step_enabled dashboard; then
        guided_completion_service_line "K8s Dashboard" "https://dashboard.$DOMAIN" "$(guided_step_live_status dashboard)"
    fi
}

sast_controller_token_configured() {
    cluster_reachable || return 1
    [ "$($KUBECTL -n "$NAMESPACE" get secret fortify-secrets \
        -o 'go-template={{ index .metadata.annotations "fortify.dev/ssc-controller-token-configured" }}' \
        2>/dev/null)" = true ]
}

guided_completion_print_next_steps() {
    local printed=0
    if guided_step_enabled ssc; then
        printf '    - SSC: sign in as admin; refer to the SSC documentation for the default password, then change it.\n'
        printed=1
    fi
    if guided_step_enabled sast_controller || guided_step_enabled sast_sensor; then
        if sast_controller_token_configured; then
            printf '    - ScanCentral SAST: SSC ControllerToken is configured in Kubernetes.\n'
        else
            printf '    - ScanCentral SAST: create an SSC ControllerToken in SSC and apply it from Configure.\n'
        fi
        printed=1
    fi
    if guided_step_enabled dast_core || guided_step_enabled dast_scanner; then
        printf '    - ScanCentral DAST: finish LIM DAST license and default pool setup when ready.\n'
        printed=1
    fi
    printf '    - Client access: import the mkcert root CA on machines that browse lab URLs.\n'
    printed=1
    [ "$printed" -eq 1 ] || printf '    - No manual next steps detected for this profile.\n'
}

guided_completion_screen() {
    local choice
    while true; do
        title "Guided deployment complete"
        cat <<EOF

  Congratulations, FortifyLab is ready.

  Your selected deployment profile completed successfully. Below is a live
  access handoff so you can open the lab, retrieve credentials deliberately,
  and finish any product-level configuration.

EOF
        guided_print_profile_summary
        echo
        section "Deployed services"
        guided_completion_print_services
        echo
        section "Recommended next steps"
        guided_completion_print_next_steps
        cat <<EOF

  1. Access & credentials
  2. Tools and FCLI readiness
  3. Certificate trust instructions
  4. View deployment plan summary
  5. View wizard log

  r. Return to main menu
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) urls_creds ;;
            2) fcli_tools_menu ;;
            3) certificate_trust_handoff ;;
            4) wizard_deployment_plan; press_any ;;
            5) wizard_log_viewer ;;
            [Rr]|"") return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

guided_deployment_menu() {
    local choice
    fortify_lab_require_acknowledgement || return 1
    if managed_releases_exist; then
        note "Existing managed releases detected; opening Resume or repair so live state drives the next step."
        press_any
        resume_repair
        return
    fi
    GUIDED_MODE_CONTEXT=fresh
    guided_profile_menu || return
    title "Guided deployment mode"
    printf '\n  %s\n' "$(guided_mode_context_text fresh)"
    guided_print_profile_summary
    cat <<EOF

  1. Interactive guided deployment
  2. Auto-advance after each verified step

  Auto-advance still pauses for manual configuration and lets you press i
  during wait screens or countdowns to take interactive control.

EOF
    ask choice "Select:"
    case "$choice" in
        2) GUIDED_AUTO_ADVANCE=1; GUIDED_MODE_CONTEXT=fresh; wizard_log_event "action=guided_mode_start mode=auto"; guided_deployment 0 ;;
        *) GUIDED_AUTO_ADVANCE=0; GUIDED_MODE_CONTEXT=fresh; wizard_log_event "action=guided_mode_start mode=fresh"; guided_deployment 0 ;;
    esac
}

guided_deployment() {
    local idx="${1:-0}" choice id total="${#GUIDED_STEP_ID[@]}" result next_label transition_reason completed_idx
    fortify_lab_require_acknowledgement || return 1
    wizard_log_event "action=guided_session_start mode=${GUIDED_MODE_CONTEXT:-fresh} start_index=$idx auto_advance=${GUIDED_AUTO_ADVANCE:-0}"
    while [ "$idx" -lt "$total" ]; do
        id="${GUIDED_STEP_ID[$idx]}"

        if [ "${GUIDED_AUTO_ADVANCE:-0}" = "1" ] && ! guided_step_is_manual "$id"; then
            transition_reason="already complete"
            if ! guided_step_live_complete "$id"; then
                guided_run_and_verify "$id" "${GUIDED_STEP_LABEL[$idx]}"
                result=$?
                case "$result" in
                    0) transition_reason="verified" ;;
                    2) GUIDED_AUTO_ADVANCE=0; continue ;;
                    3) return ;;
                    4) continue ;;
                    *) GUIDED_AUTO_ADVANCE=0; press_any; continue ;;
                esac
            fi
            completed_idx="$idx"
            idx=$((idx + 1))
            if [ "$idx" -lt "$total" ]; then
                next_label="${GUIDED_STEP_LABEL[$idx]}"
                guided_countdown "$completed_idx" "${GUIDED_STEP_LABEL[$completed_idx]}" "$idx" "$next_label" "$transition_reason" || continue
            fi
            continue
        fi

        title "Guided deployment - Step $((idx + 1)) of $total"
        printf '\n  %s\n' "$(guided_mode_context_text "$GUIDED_MODE_CONTEXT")"
        printf '\n  %s%s%s\n\n  %s\n' "$BOLD" "${GUIDED_STEP_LABEL[$idx]}" "$RESET" "${GUIDED_STEP_HELP[$idx]}"
        printf '  Step type: %s\n' "$(guided_step_action_profile "$id")"
        printf '\n  Current status: %s\n' "$(guided_step_live_status "$id")"
        printf '  Why pending: %s\n' "$(guided_step_why_pending "$id")"
        [ "$id" = dashboard ] && printf '  Dashboard URL: https://dashboard.%s\n' "$DOMAIN"
        [ "${GUIDED_AUTO_ADVANCE:-0}" = "1" ] && printf '  Mode: auto-advance is paused for this step\n'
        echo
        if guided_step_complete "$id"; then
            echo "  n. Next"
            echo "  r. Run again"
            echo "  w. Watch verification"
        elif guided_step_in_progress "$id"; then
            echo "  w. Watch verification"
            echo "  r. Retry operation"
        else
            echo "  r. Run"
            echo "  t. Retry"
        fi
        [ "${GUIDED_STEP_OPTIONAL[$idx]}" -eq 1 ] && echo "  s. Skip optional step"
        [ "${GUIDED_AUTO_ADVANCE:-0}" = "0" ] && echo "  a. Enable auto-advance"
        [ "${GUIDED_AUTO_ADVANCE:-0}" = "1" ] && echo "  i. Stay interactive"
        [ "$idx" -gt 0 ] && echo "  b. Back"
        guided_step_has_pod_logs "$id" && echo "  p. Pod logs"
        echo "  l. View wizard log"
        echo "  d. Live diagnostics"
        echo "  x. Export diagnostics bundle"
        echo "  ?. Help for this step"
        echo "  q. Quit safely"
        echo
        ask choice "Select:"
        case "$choice" in
            [Nn])
                if guided_step_complete "$id" || guided_step_is_optional "$id"; then
                    idx=$((idx + 1))
                else
                    error "Run this required step before continuing"
                    sleep 1
                fi
                ;;
            [Rr]|[Tt])
                guided_run_and_verify "$id" "${GUIDED_STEP_LABEL[$idx]}"
                result=$?
                if [ "$result" -eq 0 ] && { guided_step_is_optional "$id" || guided_step_complete "$id"; }; then
                    idx=$((idx + 1))
                elif [ "$result" -eq 3 ]; then
                    return
                elif [ "$result" -eq 4 ]; then
                    continue
                else
                    press_any
                fi
                ;;
            [Ww])
                guided_wait_for_step "$id" "${GUIDED_STEP_LABEL[$idx]}"
                result=$?
                if [ "$result" -eq 0 ]; then
                    if guided_step_is_optional "$id" || guided_step_complete "$id"; then
                        idx=$((idx + 1))
                    fi
                elif [ "$result" -eq 3 ]; then
                    return
                elif [ "$result" -eq 4 ]; then
                    continue
                else
                    press_any
                fi
                ;;
            [Aa]) GUIDED_AUTO_ADVANCE=1 ;;
            [Ii]) GUIDED_AUTO_ADVANCE=0 ;;
            [Pp])
                if guided_step_has_pod_logs "$id"; then
                    wizard_log_event "action=user_control step=$id control=pod_logs"
                    guided_step_pod_logs "$id" "${GUIDED_STEP_LABEL[$idx]}"
                else
                    note "No pod logs apply to ${GUIDED_STEP_LABEL[$idx]} yet."
                    press_any
                fi
                ;;
            [Ll]) wizard_log_event "action=user_control step=$id control=view_log"; wizard_log_viewer ;;
            [Dd]) wizard_log_event "action=user_control step=$id control=live_diagnostics"; guided_live_diagnostics "$id" "${GUIDED_STEP_LABEL[$idx]}"; press_any ;;
            [Xx]) wizard_log_event "action=user_control step=$id control=diagnostics_bundle"; guided_diagnostics_bundle; press_any ;;
            [Ss])
                if guided_step_is_optional "$id"; then
                    GUIDED_WAIT_LAST_STATE="skipped"
                    note "Skipped optional step; you can return to it later."
                    wizard_log_event "action=step_exit step=$id state=skipped"
                    idx=$((idx + 1))
                else
                    error "${GUIDED_STEP_LABEL[$idx]} is required and cannot be skipped"
                    sleep 1
                fi
                ;;
            [Bb]) [ "$idx" -gt 0 ] && idx=$((idx - 1)) ;;
            \?) help_show_topic "$(guided_step_help_topic "$id")" ;;
            [Qq]) note "No wizard state or secrets were written. Live resources will be detected when you resume."; wizard_log_event "action=user_control step=$id control=quit_safely"; return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
    wizard_log_event "action=guided_session_end mode=${GUIDED_MODE_CONTEXT:-fresh} state=complete"
    guided_completion_screen
}


resume_repair() {
    local idx id start=0 found=0 total="${#GUIDED_STEP_ID[@]}"
    fortify_lab_require_acknowledgement || return 1
    GUIDED_MODE_CONTEXT=resume
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
    title "Resume or repair deployment"
    printf '
  %s
' "$(guided_mode_context_text resume)"
    echo
    echo "  State is derived from current files and Kubernetes; no password or token is persisted."
    guided_print_profile_summary
    echo
    guided_collect_step_statuses
    echo
    section "Deployment state"
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        id="${GUIDED_STEP_ID[$idx]}"
        printf '  %2d. %-30s %s
' "$((idx + 1))" "${GUIDED_STEP_LABEL[$idx]}" "$(guided_cached_step_status "$idx")"
        if [ "$found" -eq 0 ] && [ "${GUIDED_STEP_OPTIONAL[$idx]}" -eq 0 ] && ! guided_cached_step_complete "$idx"; then
            start="$idx"
            found=1
        fi
    done
    echo
    note "Guided mode will start at the first incomplete required step; completed steps remain available for repair."
    note "$(guided_repair_recommendation "${GUIDED_STEP_ID[$start]}")"
    press_any
    guided_deployment "$start"
}

deploy_from_scratch() {
    fortify_lab_require_acknowledgement || return 1
    GUIDED_MODE_CONTEXT=fresh
    title "Deploy lab from scratch"
    fresh_deployment_guard || { press_any; return 1; }
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

    guided_run_and_verify preflight "Pre-flight" || return
    guided_run_and_verify certs "Certs" || return
    guided_run_and_verify dashboard "Dashboard" || return
    guided_run_and_verify secrets "Secrets" || return
    guided_run_and_verify mysql "MySQL" || return
    guided_run_and_verify postgresql "PostgreSQL" || return
    guided_run_and_verify ssc "SSC" || return
    guided_run_and_verify lim "LIM" || return
    guided_run_and_verify sast "SAST" || return
    guided_run_and_verify dast "DAST" || return
    note "Deploy complete. Use Advanced setup and configuration for DNS, the SSC token, and LIM."
    press_any
}

preflight_capacity_is_integer() {
    [[ "${1:-}" =~ ^[0-9]+$ ]]
}

preflight_memory_gib() {
    awk '/MemTotal:/ {print int($2/1024/1024)}' /proc/meminfo 2>/dev/null
}

preflight_disk_gib() {
    df -Pk "$FORTIFY_HOME_K8S" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}'
}

preflight_resource_warnings() {
    local memory_gib disk_gib
    memory_gib=$(preflight_memory_gib)
    disk_gib=$(preflight_disk_gib)
    if ! preflight_capacity_is_integer "$memory_gib"; then
        printf '%s\n' "Host memory is unknown; recommended minimum is ${FORTIFY_RECOMMENDED_MEMORY_GIB} GiB."
    elif [ "$memory_gib" -lt "$FORTIFY_RECOMMENDED_MEMORY_GIB" ]; then
        printf '%s\n' "Host memory is ${memory_gib} GiB; recommended minimum is ${FORTIFY_RECOMMENDED_MEMORY_GIB} GiB."
    fi
    if ! preflight_capacity_is_integer "$disk_gib"; then
        printf '%s\n' "Free disk is unknown; recommended minimum is ${FORTIFY_RECOMMENDED_DISK_GIB} GiB."
    elif [ "$disk_gib" -lt "$FORTIFY_RECOMMENDED_DISK_GIB" ]; then
        printf '%s\n' "Free disk is ${disk_gib} GiB; recommended minimum is ${FORTIFY_RECOMMENDED_DISK_GIB} GiB."
    fi
}


preflight_can_prompt_for_low_resources() {
    [ "${GUIDED_AUTO_ADVANCE:-0}" != 1 ] && [ "${FORTIFY_NONINTERACTIVE:-0}" != 1 ] && [ -t 0 ]
}

preflight_confirm_low_resources() {
    local warnings
    warnings=$(preflight_resource_warnings)
    [ -z "$warnings" ] && return 0
    wizard_log_event "action=resource_warning state=detected"
    printf '\n%s\n' "$warnings" >&2
    if [ "${FORTIFY_ALLOW_LOW_RESOURCES:-0}" = 1 ]; then
        note "Continuing below the recommended host profile because FORTIFY_ALLOW_LOW_RESOURCES=1 is set."
        wizard_log_event "action=resource_warning state=allowed mode=env_override"
        return 0
    fi
    if ! preflight_can_prompt_for_low_resources; then
        error "Resource warnings require FORTIFY_ALLOW_LOW_RESOURCES=1 in auto-advance or non-interactive mode."
        wizard_log_event "action=resource_warning state=blocked mode=noninteractive"
        return 1
    fi
    printf '%s %s\n' "$WARN_MARK" "Resource warnings do not block lab deployment if you explicitly continue." >&2
    if confirm "Continue below the recommended RAM/disk profile?"; then
        wizard_log_event "action=resource_warning state=allowed mode=interactive"
        return 0
    fi
    wizard_log_event "action=resource_warning state=blocked mode=interactive"
    return 1
}


preflight_check() {
    local command variable
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
    preflight_confirm_low_resources || return 1
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
# First-time welcome
# ============================================================

fortifylab_state_path() {
    local state_root
    if [ -n "${XDG_STATE_HOME:-}" ]; then
        state_root="$XDG_STATE_HOME"
    else
        state_root="${HOME:?HOME is required}/.local/state"
    fi
    printf '%s/fortify-lab/%s\n' "$state_root" "$1"
}

fortifylab_status_word() {
    case "$1" in
        ok) printf '%s\n' "${GREEN}ready${RESET}" ;;
        warn) printf '%s\n' "${YELLOW}attention needed${RESET}" ;;
        *) printf '%s\n' "${DIM}unknown${RESET}" ;;
    esac
}

fortifylab_welcome_intro() {
    fortify_lab_welcome_banner
    cat <<'EOF'

Welcome. Fortify Lab builds a local, ready-to-scan Fortify training lab on
MicroK8s so you can learn the product flow, run scans, and reset the
infrastructure without designing a production platform first.

Recommended path:
  1. Review host requirements and license files.
  2. Choose the deployment profile you actually want to run.
  3. Let Guided deployment install, verify, and wait for each component.
  4. Open deployed URLs, retrieve credentials deliberately, and run a first scan.

Core components:
  - SSC stores results and manages application security data.
  - ScanCentral SAST provides controller, work platform, and sensors for SAST.
  - ScanCentral DAST uses LIM and WebInspect licensing for DAST scans.
  - The Kubernetes Dashboard helps inspect pods, logs, and cluster state.
EOF
}

fortifylab_welcome_warnings() {
    cat <<'EOF'
Before you begin:
  - Run this wizard as your normal user, not with sudo.
  - This is a lab and training environment, not a production architecture.
  - Use lab-only data, credentials, and scan targets.
  - Sample applications, when installed, are intentionally vulnerable.
  - DAST workflows require ScanCentral DAST and WebInspect licenses in LIM.
EOF
}

fortifylab_license_input_path() {
    if [ -n "${FORTIFY_LICENSE_FILE:-}" ]; then
        printf '%s\n' "$FORTIFY_LICENSE_FILE"
    else
        printf '%s/secrets/input/fortify.license\n' "$FORTIFY_HOME_K8S"
    fi
}

fortifylab_welcome_locations() {
    local log_file diagnostics_dir
    log_file="$(fortify_wizard_log_file 2>/dev/null || fortifylab_state_path wizard.log)"
    diagnostics_dir="$(fortifylab_state_path diagnostics)"
    cat <<EOF
Helpful locations:
  - Repository:      $FORTIFY_HOME_K8S
  - Environment:     $ENV_FILE
  - Env backups:     $ENV_BACKUP_DIR
  - License input:   $(fortifylab_license_input_path)
  - TLS files:       $FORTIFY_HOME_K8S/certs
  - Wizard log:      $log_file
  - Diagnostics:     $diagnostics_dir
EOF
}

fortifylab_welcome_snapshot() {
    local env_status license_status docker_status microk8s_status domain profile
    [ -f "$ENV_FILE" ] && env_status=ok || env_status=warn
    if ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" && fortify_resolve_license_file >/dev/null ) 2>/dev/null; then
        license_status=ok
    else
        license_status=warn
    fi
    command -v docker >/dev/null 2>&1 && docker_status=ok || docker_status=warn
    command -v microk8s >/dev/null 2>&1 && microk8s_status=ok || microk8s_status=warn
    domain="${DOMAIN:-<unset>}"
    profile="${GUIDED_DEPLOYMENT_PROFILE_LABEL:-$(guided_profile_label "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}")}"

    cat <<EOF
Quick environment snapshot:
  - .env:            $(fortifylab_status_word "$env_status")
  - License:         $(fortifylab_status_word "$license_status")
  - Docker:          $(fortifylab_status_word "$docker_status")
  - MicroK8s:        $(fortifylab_status_word "$microk8s_status")
  - Domain:          $domain
  - Profile:         $profile
EOF
}

fortifylab_first_time_welcome_content() {
    fortifylab_welcome_intro
    printf '\n'
    fortifylab_welcome_warnings
    printf '\n'
    fortifylab_welcome_locations
    printf '\n'
    fortifylab_welcome_snapshot
}

fortifylab_first_time_welcome_menu() {
    [ "${FORTIFY_SKIP_WELCOME:-0}" = "1" ] && return 0
    [ -t 0 ] && [ -t 1 ] || return 0

    while true; do
        title "Welcome to FortifyLab"
        fortifylab_first_time_welcome_content
        section "Next steps"
        echo "   1. Start guided setup"
        echo "   2. Review requirements"
        echo "   3. Choose deployment profile"
        echo "   4. Open Help Center"
        echo "   5. Advanced setup and configuration"
        echo
        echo "   r. Continue to main menu"
        echo "   q. Quit"
        echo
        ask choice "Select:"
        case "$choice" in
            1) guided_deployment_menu; return ;;
            2) title "Requirements"; fortifylab_welcome_warnings; printf '\n'; fortifylab_welcome_locations; printf '\n'; fortifylab_welcome_snapshot; press_any ;;
            3) guided_profile_menu ;;
            4) help_center ;;
            5) advanced_menu ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid choice"; sleep 1 ;;
        esac
    done
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
        echo "   5. Sample applications"
        echo "   6. Kubernetes Dashboard access"

        section "Diagnostics and advanced"
        echo "   7. Diagnostics / live status"
        echo "   8. Advanced setup and configuration"

        section "Operations"
        echo "   9. Lab lifecycle controls"
        echo "  10. Stream logs (all pods)"
        echo "  11. Cluster snapshot"
        echo "  12. Tail one pod"
        echo "  13. URLs & credentials"
        echo "  14. Tools and FCLI readiness"
        echo "  15. Image versions"
        echo "  16. Configuration editor"

        section "Learn"
        echo "  17. Help Center / Fortify Knowledge Center"
        echo "  18. Operational guidance and troubleshooting"
        echo "  19. View wizard log"

        echo
        echo "   q. Quit"
        echo
        ask choice "Select:"

        case "$choice" in
            1)  guided_deployment_menu ;;
            2)  deploy_from_scratch ;;
            3)  resume_repair ;;
            4)  apps_menu ;;
            5)  sample_apps_menu ;;
            6)  dashboard_access_menu ;;
            7)  live_status ;;
            8)  advanced_menu ;;
            9)  lab_lifecycle_menu ;;
           10)  stream_logs ;;
           11)  cluster_status ;;
           12)  logs_menu ;;
           13)  urls_creds ;;
           14)  fcli_tools_menu ;;
           15)  versions_menu ;;
           16)  edit_env ;;
           17)  help_center ;;
           18)  operational_guidance_menu ;;
           19)  wizard_log_viewer ;;
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
  ./start_wizard.sh doctor           Run a read-only health summary and exit.
  ./start_wizard.sh config-diagnostics
                                      Inspect .env host/URL wiring without printing secrets.
  ./start_wizard.sh -h | --help      Show this message.

Environment overrides:
  FORTIFY_HOME_K8S    Repo root (defaults to the script's directory).
  EDITOR              Editor used by the raw .env editor fallback (defaults to nano).
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
        doctor|config-diagnostics|''|--accept-lab-use) ;;
        *) error "Unsupported argument: ${1}"; usage >&2; exit 2 ;;
    esac
    if [ "$#" -gt 1 ]; then
        error "Only one command-line option is supported."
        usage >&2
        exit 2
    fi
    if [ "${1:-}" = doctor ]; then
        wizard_doctor
        exit $?
    fi
    if [ "${1:-}" = config-diagnostics ]; then
        wizard_config_diagnostics
        exit $?
    fi
    fortify_lab_detect_accept_flag "$@"
    first_launch=0
    fortify_lab_is_acknowledged || first_launch=1
    fortify_lab_require_acknowledgement || exit 1
    bootstrap_env
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
    if [ "$first_launch" -eq 1 ]; then
        fortifylab_first_time_welcome_menu
    fi
    main_menu
fi
