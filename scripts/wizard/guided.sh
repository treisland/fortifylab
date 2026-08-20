#!/usr/bin/env bash
# shellcheck shell=bash

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

# Live run-time status board (see guided_wait_render). Keyed by step id, not
# array index, so callers can touch a step's state without it needing to be a
# member of whatever profile happens to be active in GUIDED_STEP_ID right now.
#
# Must be -gA (global), not just -A: this file is sourced from inside
# source_wizard_module() in start_wizard.sh, a bash function. A bare
# `declare -A` inside a function creates a variable local to that function's
# call frame, which is destroyed the instant sourcing finishes. Every
# subsequent `GUIDED_STEP_BOARD_STATE[$id]=...` assignment then silently
# auto-vivifies a *new*, plain (non-associative) global array instead --
# and since bash evaluates non-numeric subscripts on a plain array as
# arithmetic (an unrecognized name reads as 0), every string key collapses
# onto index 0. The practical symptom was every row on the status board
# showing the same (last-write) state, which reads as "everything pending".
declare -gA GUIDED_STEP_BOARD_STATE=()
declare -gA GUIDED_STEP_STARTED_AT=()
declare -gA GUIDED_STEP_ELAPSED_FINAL=()

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
        sample_apps) printf '%s\n' "Sample applications only" ;;
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
        sample_apps) printf '%s\n' "sample_apps" ;;
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
    printf '  6. Sample applications only\n'
    printf '  7. Custom\n\n'
    printf '  r. Return\n\n'
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
        [Rr]|[Qq]) return 1 ;;
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
    flight_plan_tool show "$(flight_plan_selected_id)" >/dev/null 2>&1 || return 1
    ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
      fortify_resolve_license_file ) >/dev/null 2>&1
}

deployment_inputs_menu() {
    while true; do
        title "Configuration and license"
        printf '\n  .env:    %s\n' "$ENV_FILE"
        printf '  License: %s\n' "$(status_license)"
        flight_plan_current_status
        echo
        echo "  1. Configuration editor"
        echo "  2. Add or review the Fortify license"
        echo "  3. Deployment versions and Flight Plan"
        echo "  ?. Help for this step"
        echo "  r. Return to the guided step"
        echo
        ask choice "Select:"
        case "$choice" in
            1) edit_env ;;
            2) license_menu ;;
            3) flight_plan_versions_menu ;;
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
    for variable in DOMAIN NAMESPACE DEFAULT_PASS FORTIFY_FLIGHT_PLAN FORTIFY_SSC_CHART_VERSION \
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

sast_sensor_workload_names() {
    printf '%s\n' scancentral-sast-sensor-linux scancentral-sast-sensor scancentral-sast-worker-linux
}

sast_sensor_workload_ready() {
    local name
    for name in $(sast_sensor_workload_names); do
        if workload_ready "$NAMESPACE" statefulset "$name"; then
            return 0
        fi
    done
    return 1
}

sast_sensor_workload_in_progress() {
    local name
    for name in $(sast_sensor_workload_names); do
        if statefulset_in_progress "$NAMESPACE" "$name"; then
            return 0
        fi
    done
    return 1
}

sast_sensor_pending_detail() {
    local name existing=""
    cluster_reachable || { printf '%s\n' "Cluster is not reachable while checking the SAST sensor."; return 0; }
    if ! sast_controller_ready; then
        printf '%s\n' "Waiting for the SAST controller StatefulSet before checking the sensor."
        return 0
    fi
    for name in $(sast_sensor_workload_names); do
        if resource_exists "$NAMESPACE" statefulset "$name"; then
            existing="$existing $name"
        fi
    done
    if [ -z "$existing" ]; then
        printf 'No SAST sensor StatefulSet found. Checked: %s.\n' "$(sast_sensor_workload_names | paste -sd ' ' -)"
    else
        printf 'Waiting for SAST sensor StatefulSet readiness. Found:%s.\n' "$existing"
    fi
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
    sast_controller_ready && sast_sensor_workload_ready
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
        sast_sensor|sast) sast_sensor_ready ;;
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
        sast_sensor|sast) sast_sensor_workload_in_progress || { sast_controller_ready && pod_prefix_in_progress scancentral-sast-sensor; } ;;
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
        failed) printf '%sfailed%s' "$RED" "$RESET" ;;
        skipped) printf '%sskipped%s' "$DIM" "$RESET" ;;
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
        # Also populate the persistent board from this same derivation pass,
        # so resume's summary and the board guided_deployment shows next
        # can't disagree with each other.
        guided_board_touch "$id" "$state"
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

# ---- Persistent run status board -------------------------------------------
# A step only appears as a board row once it has been reset/touched below; the
# wait-loop renderer skips ids with no board entry. That means a full guided
# run (which resets the whole GUIDED_STEP_ID list up front) shows every step,
# while a narrower caller that only touches a handful of ids naturally shows
# just those rows instead of a misleading "pending" line for unrelated steps.

guided_board_reset() {
    # Reuse guided_step_live_state's complete/in_progress/manual/pending
    # classification rather than re-deriving a narrower copy here. The
    # earlier inline version had no in_progress branch, so any step that was
    # genuinely mid-flight from a prior/interrupted session (e.g. resume)
    # was misreported as pending until this session happened to touch it.
    local ids=("$@") id
    [ "${#ids[@]}" -gt 0 ] || ids=("${GUIDED_STEP_ID[@]}")
    GUIDED_STEP_BOARD_STATE=()
    GUIDED_STEP_STARTED_AT=()
    GUIDED_STEP_ELAPSED_FINAL=()
    for id in "${ids[@]}"; do
        GUIDED_STEP_BOARD_STATE[$id]=$(guided_step_live_state "$id")
    done
}

guided_board_touch() {
    local id="$1" state="$2"
    GUIDED_STEP_BOARD_STATE[$id]="$state"
    case "$state" in
        in_progress)
            GUIDED_STEP_STARTED_AT[$id]="$SECONDS"
            ;;
        complete|failed)
            if [ -n "${GUIDED_STEP_STARTED_AT[$id]:-}" ]; then
                GUIDED_STEP_ELAPSED_FINAL[$id]=$((SECONDS - GUIDED_STEP_STARTED_AT[$id]))
            fi
            ;;
    esac
}

guided_board_duration() {
    local id="$1" state="${GUIDED_STEP_BOARD_STATE[$1]:-pending}"
    case "$state" in
        in_progress)
            if [ -n "${GUIDED_STEP_STARTED_AT[$id]:-}" ]; then
                printf '%ss' "$((SECONDS - GUIDED_STEP_STARTED_AT[$id]))"
            else
                printf -- '--'
            fi
            ;;
        complete|failed)
            if [ -n "${GUIDED_STEP_ELAPSED_FINAL[$id]:-}" ]; then
                printf '%ss' "${GUIDED_STEP_ELAPSED_FINAL[$id]}"
            else
                printf -- '--'
            fi
            ;;
        *) printf -- '--' ;;
    esac
}

guided_board_row_line() {
    local idx="$1" active_id="$2" id label state marker
    id="${GUIDED_STEP_ID[$idx]}"
    label="${GUIDED_STEP_LABEL[$idx]}"
    state="${GUIDED_STEP_BOARD_STATE[$id]:-pending}"
    marker=' '
    [ "$id" = "$active_id" ] && marker='>'
    printf '%s %-30s %-14s %s' "$marker" "$label" "$(guided_status_render "$state")" "$(guided_board_duration "$id")"
}

guided_board_render_rows() {
    local active_id="$1" idx row_id
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        row_id="${GUIDED_STEP_ID[$idx]}"
        [ -n "${GUIDED_STEP_BOARD_STATE[$row_id]+set}" ] || continue
        printf '  %s\n' "$(guided_board_row_line "$idx" "$active_id")"
    done
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
        sast_sensor|sast) sast_sensor_workload_in_progress || { sast_controller_ready && pod_prefix_in_progress scancentral-sast-sensor; } ;;
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
        sast_sensor|sast) sast_sensor_pending_detail ;;
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
    section "Release overlays"
    release_overlay_report
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
    printf '\n%s%s%s\n' "$BOLD" "Guided deployment" "$RESET"
    printf '  %s\n' "$(guided_mode_context_text "$GUIDED_MODE_CONTEXT")"
    hr
    guided_board_render_rows "$id"
    printf '\n%s%s%s\n' "$BOLD" "Now: $label" "$RESET"
    printf '  State:   %s\n' "$(guided_step_live_status "$id")"
    printf '  Probe:   %s\n' "$probe"
    printf '  Elapsed: %ss' "$elapsed"
    [ "$timeout" -gt 0 ] && printf ' / %ss' "$timeout"
    printf '\n  Detail:  %s\n\n' "$(guided_step_progress_message "$id")"
    if declare -F guided_deployment_footer >/dev/null 2>&1; then
        guided_deployment_footer
    else
        printf '\nOptions\n  r. Retry operation\n  i. Take interactive control\n  p. Pod logs\n  l. Wizard log\n  d. Live diagnostics\n  x. Export diagnostics bundle\n  h. Help\n  q. Quit safely\n'
    fi
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
        guided_board_touch "$id" manual
        note "$label needs operator action; automatic verification is not available."
        return 0
    fi

    guided_wait_screen_enter

    started=$SECONDS
    guided_board_touch "$id" in_progress
    while true; do
        if guided_step_complete "$id"; then
            GUIDED_WAIT_LAST_STATE="complete"
            guided_board_touch "$id" complete
            guided_wait_screen_leave
            wizard_log_event "action=verification_finish step=$id probe=$probe state=complete elapsed=$((SECONDS - started))"
            note "$label verified ready."
            return 0
        fi

        elapsed=$((SECONDS - started))
        if [ "$timeout" -gt 0 ] && [ "$elapsed" -ge "$timeout" ]; then
            GUIDED_WAIT_LAST_STATE="failed"
            GUIDED_WAIT_LAST_FAILURE="$label did not verify ready within ${timeout}s; probe $probe is still failing."
            guided_board_touch "$id" failed
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
                ""|[Ii])
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
                *)
                    guided_wait_screen_leave
                    error "Unrecognized key; see options above."
                    sleep 1
                    guided_wait_screen_enter
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
    printf '\nFlight Plan:\n'
    release_overlay_report
    release_overlay_validate_selected || unavailable=1
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
    guided_board_touch "$id" in_progress
    wizard_log_event "action=step_enter step=$id label=$label mode=${GUIDED_MODE_CONTEXT:-unknown} profile=$(guided_step_action_profile "$id")"
    if ! run_deployment_operation "$id"; then
        GUIDED_WAIT_LAST_STATE="failed"
        GUIDED_WAIT_LAST_FAILURE="$label operation failed before verification."
        guided_board_touch "$id" failed
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
                ""|[Ii])
                    printf '\r\033[K'
                    GUIDED_AUTO_ADVANCE=0
                    note "[$next_num/$total] Auto-advance paused: staying interactive at $next_label."
                    return 1
                    ;;
                *)
                    printf '\r\033[K'
                    error "Unrecognized key; see options above."
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


first_scan_handoff() {
    local default_dir="${HOME:-.}/fortifylab-first-scan" choice output_dir
    title "First scan handoff"
    cat <<EOF

  This handoff prepares starter commands for a first synthetic SAST scan and a
  conservative DAST planning checklist. SSC remains the primary lab system of
  record. FoD is optional and only shown as a placeholder path.

  The generator writes local starter scripts with placeholders only. Tokens,
  passwords, client secrets, and target authorization details must be provided
  through environment variables at runtime and are not written by the wizard.

  Documentation:
    docs/operations/first-scan.md
    docs/examples/first-scan/README.md

  Default output directory:
    $default_dir

EOF
    confirm "Generate first-scan starter scripts now?" || { press_any; return; }
    ask output_dir "Output directory [$default_dir]:"
    output_dir="${output_dir:-$default_dir}"
    "$FORTIFY_HOME_K8S/docs/examples/first-scan/generate-first-scan-scripts.sh" "$output_dir" || {
        error "Could not generate first-scan starter scripts."
        press_any
        return 1
    }
    note "Generated first-scan starters in $output_dir. Review them before use."
    press_any
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
  3. First scan handoff
  4. Certificate trust instructions
  5. View deployment plan summary
  6. View wizard log

  r. Return to main menu
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) urls_creds ;;
            2) fcli_tools_menu ;;
            3) first_scan_handoff ;;
            4) certificate_trust_handoff ;;
            5) wizard_deployment_plan; press_any ;;
            6) wizard_log_viewer ;;
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
    while true; do
        title "Guided deployment mode"
        printf '\n  %s\n' "$(guided_mode_context_text fresh)"
        guided_print_profile_summary
        section "Flight Plan"
        flight_plan_current_status
        release_overlay_report
        cat <<EOF

  1. Interactive guided deployment
  2. Auto-advance after each verified step

  Auto-advance still pauses for manual configuration and lets you press i
  during wait screens or countdowns to take interactive control.

  r. Return
EOF
        ask choice "Select:"
        case "$choice" in
            1) GUIDED_AUTO_ADVANCE=0; GUIDED_MODE_CONTEXT=fresh; wizard_log_event "action=guided_mode_start mode=fresh"; guided_deployment 0; return ;;
            2)
                printf '\n'
                note "Auto-advance readiness:"
                prereqs_status_table
                printf '  %-24s %s\n' "Configuration and license" "$(prereq_status inputs_complete)"
                if [ "$(prereqs_ready_count)" -lt 4 ] || ! inputs_complete; then
                    printf '\n'
                    note "Auto-advance will pause for interactive input until the items above are ready."
                fi
                confirm "This will deploy $GUIDED_DEPLOYMENT_PROFILE_LABEL unattended, stopping only for required manual input or a failure. Continue?" || { note "Auto-advance not started."; continue; }
                GUIDED_AUTO_ADVANCE=1
                GUIDED_MODE_CONTEXT=fresh
                wizard_log_event "action=guided_mode_start mode=auto"
                guided_deployment 0
                return
                ;;
            [Rr]|[Qq]) return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

guided_deployment() {
    local idx="${1:-0}" choice id total="${#GUIDED_STEP_ID[@]}" result next_label transition_reason completed_idx
    fortify_lab_require_acknowledgement || return 1
    guided_board_reset
    wizard_log_event "action=guided_session_start mode=${GUIDED_MODE_CONTEXT:-fresh} start_index=$idx auto_advance=${GUIDED_AUTO_ADVANCE:-0}"
    while [ "$idx" -lt "$total" ]; do
        id="${GUIDED_STEP_ID[$idx]}"

        if [ "${GUIDED_AUTO_ADVANCE:-0}" = "1" ] && ! guided_step_is_manual "$id"; then
            transition_reason="already complete"
            if ! guided_step_live_complete "$id"; then
                if [ "$id" = prereqs ]; then
                    printf '  Auto-advance paused: host prerequisites need attention.\n'
                fi
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
        # Keep the persistent status board visible on the normal per-step
        # screen, not just while a step is actively being watched/verified
        # (guided_wait_render) -- otherwise resume/repair and interactive
        # navigation only ever show this one step's single-line status.
        guided_board_render_rows "$id"
        hr
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
                    guided_board_touch "$id" skipped
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
    local idx start=0 found=0 total="${#GUIDED_STEP_ID[@]}"
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
    section "Flight Plan"
    flight_plan_current_status
    release_overlay_report
    echo
    guided_collect_step_statuses
    echo
    section "Deployment state"
    # Render from the same GUIDED_STEP_BOARD_STATE that guided_deployment's
    # per-step screen and wait screen use, rather than a separate printed
    # loop over the status cache -- one state, one rendering, so this
    # summary and the board it hands off to can't drift out of sync.
    guided_board_render_rows ""
    for idx in "${!GUIDED_STEP_ID[@]}"; do
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

express_step_runnable() {
    case "$1" in
        prereqs|inputs|configure) return 1 ;;
        *) return 0 ;;
    esac
}

express_deployment_plan() {
    local idx step number=1
    section "Selected profile"
    guided_print_profile_summary
    section "Flight Plan"
    flight_plan_current_status
    release_overlay_report
    section "Express deployment plan"
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        step="${GUIDED_STEP_ID[$idx]}"
        express_step_runnable "$step" || continue
        printf '  %2d. %s (%s)\n' "$number" "${GUIDED_STEP_LABEL[$idx]}" "${GUIDED_STEP_IMPACT[$idx]}"
        number=$((number + 1))
    done
    cat <<EOF

  Express runs the selected profile with one confirmation and verifies each
  deployable step. Configuration and post-deploy integration steps remain in
  Guided deployment and Advanced setup so they can collect operator input.
EOF
}

deploy_from_scratch() {
    local idx step
    fortify_lab_require_acknowledgement || return 1
    GUIDED_MODE_CONTEXT=fresh
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
    title "Express deployment"
    fresh_deployment_guard || { press_any; return 1; }
    wizard_deployment_plan
    express_deployment_plan
    confirm "Proceed with Express deployment for $GUIDED_DEPLOYMENT_PROFILE_LABEL?" || return

    guided_board_reset
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        step="${GUIDED_STEP_ID[$idx]}"
        express_step_runnable "$step" || continue
        guided_run_and_verify "$step" "${GUIDED_STEP_LABEL[$idx]}" || return
    done
    note "Express deployment complete for $GUIDED_DEPLOYMENT_PROFILE_LABEL. Use Guided deployment or Advanced setup for post-deploy configuration."
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
    cluster_profile_confirm_target_context || return 1
    cluster_reachable || { error "Cluster not reachable"; return 1; }
    microk8s status --wait-ready >/dev/null 2>&1 || {
        error "MicroK8s is not ready"
        return 1
    }
    $KUBECTL get storageclass nfs >/dev/null 2>&1 || {
        error "Required NFS storage class is unavailable (use option 3)"
        return 1
    }
    section "Flight Plan"
    flight_plan_current_status
    release_overlay_report
    release_overlay_validate_selected || return 1
    [ -s "$HOME/.docker/config.json" ] || {
        error "Docker registry login is missing (use option 3)"
        return 1
    }
    for variable in DOMAIN NAMESPACE DEFAULT_PASS FORTIFY_FLIGHT_PLAN FORTIFY_SSC_CHART_VERSION \
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
