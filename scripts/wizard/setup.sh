#!/usr/bin/env bash
# shellcheck shell=bash

# ============================================================
# Guided setup and setup readiness
# ============================================================

SETUP_STEP_LABEL=(
    "Welcome and scope"
    "Lab identity and domain"
    "Deployment profile"
    "Fortify Flight Plan"
    "License file"
    "Registry login"
    "TLS certificates and root CA"
    "Hostname and DNS guidance"
    "fcli truststore readiness"
    "Review and apply"
)

SETUP_PENDING_UPDATES=()
SETUP_PENDING_ACTIONS=()

wizard_vertical_footer() {
    local label="${1:-Options}" item
    shift || true
    printf '\n%s\n' "$label"
    for item in "$@"; do
        printf '  %s\n' "$item"
    done
}

guided_setup_footer() {
    local step="${1:-}"
    if [ "$step" = 0 ]; then
        wizard_vertical_footer "Options" \
            "c. Continue" \
            "q. Cancel setup"
        return
    fi
    wizard_vertical_footer "Options" \
        "e. Edit values" \
        "c. Continue" \
        "s. Skip" \
        "b. Back" \
        "h. Help" \
        "q. Cancel setup"
}

guided_setup_help_topic() {
    case "$1" in
        0) printf '%s\n' overview ;;
        1) printf '%s\n' urls ;;
        2) printf '%s\n' lab-scope ;;
        3) printf '%s\n' guided/configuration ;;
        4) printf '%s\n' troubleshooting/license ;;
        5) printf '%s\n' troubleshooting/registry ;;
        6) printf '%s\n' troubleshooting/tls ;;
        7) printf '%s\n' urls ;;
        8) printf '%s\n' troubleshooting/tls ;;
        9) printf '%s\n' guided/configuration ;;
        *) printf '%s\n' overview ;;
    esac
}

guided_deployment_footer() {
    wizard_vertical_footer "Options" \
        "r. Retry operation" \
        "i. Take interactive control" \
        "p. Pod logs" \
        "l. Wizard log" \
        "d. Live diagnostics" \
        "x. Export diagnostics bundle" \
        "h. Help" \
        "q. Quit safely"
}

setup_pending_set() {
    env_pending_set SETUP_PENDING_UPDATES "$1" "$2"
}

setup_pending_unset() {
    local key="$1" pair next=()
    for pair in "${SETUP_PENDING_UPDATES[@]}"; do
        [ "${pair%%=*}" = "$key" ] && continue
        next+=("$pair")
    done
    SETUP_PENDING_UPDATES=("${next[@]}")
}

setup_pending_action_selected() {
    local wanted="$1" action
    for action in "${SETUP_PENDING_ACTIONS[@]}"; do
        [ "$action" = "$wanted" ] && return 0
    done
    return 1
}

setup_pending_action_add() {
    local action="$1"
    setup_pending_action_selected "$action" || SETUP_PENDING_ACTIONS+=("$action")
}

setup_pending_domain_value() {
    env_pending_value DOMAIN "${DOMAIN:-}" "${SETUP_PENDING_UPDATES[@]}"
}

setup_pending_license_value() {
    env_pending_value FORTIFY_LICENSE_FILE "$(fortifylab_license_input_path)" "${SETUP_PENDING_UPDATES[@]}"
}

setup_pending_tls_mode() {
    env_pending_value FORTIFY_TLS_MODE "${FORTIFY_TLS_MODE:-mkcert}" "${SETUP_PENDING_UPDATES[@]}"
}

setup_pending_byo_tls_cert() {
    env_pending_value FORTIFY_BYO_TLS_CERT "${FORTIFY_BYO_TLS_CERT:-}" "${SETUP_PENDING_UPDATES[@]}"
}

setup_pending_byo_tls_key() {
    env_pending_value FORTIFY_BYO_TLS_KEY "${FORTIFY_BYO_TLS_KEY:-}" "${SETUP_PENDING_UPDATES[@]}"
}

setup_pending_byo_tls_ca_cert() {
    env_pending_value FORTIFY_BYO_TLS_CA_CERT "${FORTIFY_BYO_TLS_CA_CERT:-}" "${SETUP_PENDING_UPDATES[@]}"
}

setup_profile_value() {
    env_pending_value FORTIFY_DEPLOYMENT_PROFILE "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}" "${SETUP_PENDING_UPDATES[@]}"
}

setup_profile_label() {
    guided_profile_label "$(setup_profile_value)"
}

setup_flight_plan_value() {
    env_pending_value FORTIFY_FLIGHT_PLAN "$(flight_plan_selected_id)" "${SETUP_PENDING_UPDATES[@]}"
}

setup_flight_plan_ready() {
    flight_plan_tool validate >/dev/null 2>&1 || return 1
    flight_plan_tool show "$(setup_flight_plan_value)" >/dev/null 2>&1
}

setup_license_ready() {
    ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" &&
      fortify_resolve_license_file ) >/dev/null 2>&1
}

setup_flight_plan_status() {
    local current pending
    current="$(flight_plan_selected_id)"
    pending="$(setup_flight_plan_value)"
    printf '  Current Flight Plan: %s\n' "$current"
    printf '  Pending Flight Plan: %s\n' "$pending"
    printf '  Current alignment:   %s\n' "$(flight_plan_alignment_summary "$current")"
    if setup_flight_plan_ready; then
        printf '  Catalog status:      selected plan exists\n'
    else
        printf '  Catalog status:      selected plan needs review\n'
    fi
}

setup_profile_preview() {
    local profile="${1:-$(setup_profile_value)}" saved_profile saved_components saved_label id idx active_ids=" "
    saved_profile="$GUIDED_DEPLOYMENT_PROFILE"
    saved_components="$GUIDED_DEPLOYMENT_COMPONENTS"
    saved_label="$GUIDED_DEPLOYMENT_PROFILE_LABEL"
    guided_apply_deployment_profile "$profile"
    printf 'Profile: %s\n' "$GUIDED_DEPLOYMENT_PROFILE_LABEL"
    printf '\nWill deploy\n'
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        id="${GUIDED_STEP_ID[$idx]}"
        case "$id" in prereqs|inputs|configure) continue ;; esac
        printf '  - %s\n' "${GUIDED_STEP_LABEL[$idx]}"
        active_ids="$active_ids$id "
    done
    printf '\nWill not deploy\n'
    for idx in "${!GUIDED_ALL_STEP_ID[@]}"; do
        id="${GUIDED_ALL_STEP_ID[$idx]}"
        case "$id" in prereqs|inputs|preflight|certs|dashboard|secrets|configure) continue ;; esac
        case "$active_ids" in *" $id "*) continue ;; esac
        printf '  - %s\n' "${GUIDED_ALL_STEP_LABEL[$idx]}"
    done
    GUIDED_DEPLOYMENT_PROFILE="$saved_profile"
    GUIDED_DEPLOYMENT_COMPONENTS="$saved_components"
    GUIDED_DEPLOYMENT_PROFILE_LABEL="$saved_label"
    guided_apply_deployment_profile "$saved_profile"
}

setup_status_line() {
    local state="$1" label="$2" detail="${3:-}"
    if [ "$state" = ready ]; then
        printf '  %s %s' "$OK_MARK" "$label"
    else
        printf '  %s %s' "$WARN_MARK" "$label"
    fi
    [ -z "$detail" ] || printf ' - %s' "$detail"
    printf '\n'
}

setup_docker_auth_ready() {
    local config
    docker_ready || return 1
    config=$(materialize_registry_auth_config 2>/dev/null) || return 1
    rm -f "$config"
}

setup_regcred_ready() {
    cluster_reachable || return 1
    resource_exists "${NAMESPACE:-fortify}" secret regcred
}

setup_root_ca_exported() {
    [ -s "$FORTIFY_HOME_K8S/certs/rootCA.pem" ]
}

setup_fcli_trust_ready() {
    if declare -F fcli_trust_configured_current >/dev/null 2>&1 && fcli_trust_configured_current >/dev/null 2>&1; then
        return 0
    fi
    [ -n "${FCLI_TRUSTSTORE:-}" ] && [ -s "$FCLI_TRUSTSTORE" ] && return 0
    [ -n "${TRUSTSTORE:-}" ] && [ -s "$TRUSTSTORE" ] && return 0
    [ -s "$FORTIFY_HOME_K8S/certs/truststore" ]
}

setup_readiness_score() {
    local total=11 ready=0
    [ -s "$ENV_FILE" ] && ready=$((ready + 1))
    env_config_valid && ready=$((ready + 1))
    [ -n "$(setup_profile_value)" ] && ready=$((ready + 1))
    setup_flight_plan_ready && ready=$((ready + 1))
    setup_license_ready && ready=$((ready + 1))
    setup_docker_auth_ready && ready=$((ready + 1))
    setup_regcred_ready && ready=$((ready + 1))
    certs_ready && ready=$((ready + 1))
    setup_root_ca_exported && ready=$((ready + 1))
    setup_fcli_trust_ready && ready=$((ready + 1))
    cluster_reachable && ready=$((ready + 1))
    printf '%s/%s\n' "$ready" "$total"
}

setup_readiness_items() {
    [ -s "$ENV_FILE" ] && setup_status_line ready ".env file exists" "$ENV_FILE" || setup_status_line warn ".env file exists" "copy .env.example first"
    env_config_valid && setup_status_line ready "Domain and URLs are valid" || setup_status_line warn "Domain and URLs are valid" "repair derived values from DOMAIN"
    [ -n "$(setup_profile_value)" ] && setup_status_line ready "Deployment profile selected" "$(setup_profile_label)" || setup_status_line warn "Deployment profile selected" "choose a profile"
    setup_flight_plan_ready && setup_status_line ready "Fortify Flight Plan selected" "$(setup_flight_plan_value)" || setup_status_line warn "Fortify Flight Plan selected" "choose a curated plan or repair the catalog"
    setup_license_ready && setup_status_line ready "Fortify license is readable" || setup_status_line warn "Fortify license is readable" "add or point to fortify.license"
    setup_docker_auth_ready && setup_status_line ready "Docker registry auth is usable" || setup_status_line warn "Docker registry auth is usable" "run Docker login or refresh credentials"
    setup_regcred_ready && setup_status_line ready "Kubernetes image pull secret exists" || setup_status_line warn "Kubernetes image pull secret exists" "refresh regcred after cluster is ready"
    certs_ready && setup_status_line ready "Lab TLS artifacts exist" || setup_status_line warn "Lab TLS artifacts exist" "generate TLS certificates"
    setup_root_ca_exported && setup_status_line ready "Public mkcert root CA exported" || setup_status_line warn "Public mkcert root CA exported" "export certs/rootCA.pem for client trust"
    setup_fcli_trust_ready && setup_status_line ready "fcli truststore is available" || setup_status_line warn "fcli truststore is available" "configure fcli lab trust"
    cluster_reachable && setup_status_line ready "Kubernetes cluster is reachable" || setup_status_line warn "Kubernetes cluster is reachable" "start MicroK8s or check kube context"
}

setup_readiness_guidance() {
    printf '
Readiness guidance
'
    printf '
License
'
    printf '  Configured: %s
' "$(setup_pending_license_value)"
    setup_license_ready && printf '  Verified:   readable, non-empty license file
  Next:       continue
' || printf '  Verified:   missing or unreadable
  Impact:     deployment cannot create complete Fortify secrets
  Next:       choose an external license path or import the file
'
    printf '
Registry
'
    setup_docker_auth_ready && printf '  Docker login: ready
' || printf '  Docker login: needs attention
'
    setup_regcred_ready && printf '  Kubernetes regcred: ready
  Next:       continue
' || printf '  Kubernetes regcred: missing or not verified
  Impact:     Kubernetes may fail to pull Fortify images
  Next:       refresh Kubernetes registry secret after cluster access is ready
'
    printf '
TLS and trust
'
    printf '  TLS mode:   %s
' "$(setup_tls_mode_label)"
    certs_ready && printf '  Generated artifacts: ready
' || printf '  Generated artifacts: need generation
'
    setup_root_ca_exported && printf '  Browser root CA export: ready
' || printf '  Browser root CA export: not exported
'
    setup_fcli_trust_ready && printf '  fcli trust: ready or truststore available
' || printf '  fcli trust: not configured
'
    printf '  Next:       regenerate TLS artifacts and refresh Kubernetes secrets after TLS changes
'
}

setup_readiness_summary() {
    title "Setup readiness"
    printf '
Setup readiness: %s

' "$(setup_readiness_score)"
    setup_readiness_items
    setup_readiness_guidance
    printf '
Selected deployment profile
'
    setup_profile_preview "$(setup_profile_value)"
    printf '
Selected Fortify Flight Plan
'
    setup_flight_plan_status
}

setup_license_assistant() {
    local choice src resolved default_file
    default_file="$FORTIFY_HOME_K8S/secrets/input/fortify.license"
    while true; do
        title "License file"
        printf '\nConfigured license input: %s\n' "$(fortifylab_license_input_path)"
        printf 'Pending license input:    %s\n\n' "$(setup_pending_license_value)"
        if [ -s "$(setup_pending_license_value)" ]; then
            printf '  %s Pending Fortify license path is readable\n' "$OK_MARK"
        else
            printf '  %s Pending Fortify license path is unavailable\n' "$FAIL_MARK"
        fi
        wizard_vertical_footer "License actions" \
            "1. Use an external license file path" \
            "2. Import to the repository-local input path" \
            "3. Where to obtain a license" \
            "b. Back"
        echo
        ask choice "Select:"
        case "$choice" in
            1)
                ask src "Path to fortify.license file:"
                [ -n "$src" ] || continue
                if [ ! -s "$src" ]; then
                    error "The selected file is missing, unreadable, or empty."
                    sleep 1
                    continue
                fi
                resolved="$(realpath -- "$src")" || { error "Could not resolve selected license path."; sleep 1; continue; }
                setup_pending_set FORTIFY_LICENSE_FILE "$resolved"
                note "External Fortify license path staged."
                ;;
            2)
                ask src "Path to fortify.license file:"
                [ -n "$src" ] || continue
                if [ ! -s "$src" ]; then
                    error "The selected file is missing, unreadable, or empty."
                    sleep 1
                    continue
                fi
                mkdir -p "$(dirname "$default_file")"
                cp "$src" "$default_file" || { error "Could not import license file."; sleep 1; continue; }
                setup_pending_set FORTIFY_LICENSE_FILE "$default_file"
                note "Imported license file and staged repository-local license path."
                ;;
            3) license_menu ;;
            [Bb]|"") return 0 ;;
            *) error "Invalid license action"; sleep 1 ;;
        esac
    done
}

setup_registry_status() {
    printf '\nDocker config: %s\n' "$(docker_config_path)"
    setup_docker_auth_ready && printf 'Docker Hub credentials: detected and materializable for Kubernetes\n' || printf 'Docker Hub credentials: not ready\n'
    setup_regcred_ready && printf 'Kubernetes regcred: present in namespace %s\n' "${NAMESPACE:-fortify}" || printf 'Kubernetes regcred: missing or cluster unavailable\n'
    cat <<'EOF'

Secrets are never printed. If local Docker can pull but Kubernetes cannot,
refresh the Kubernetes image pull secret after logging in.
EOF
}

setup_registry_login() {
    local username secret
    command -v docker >/dev/null 2>&1 || { error "Docker is not installed."; return 1; }
    ask username "Docker Hub username:"
    [ -n "$username" ] || return 0
    read -rsp "Docker Hub password or access token: " secret
    echo
    [ -n "$secret" ] || { note "Docker login cancelled."; return 0; }
    printf '%s\n' "$secret" | docker login --username "$username" --password-stdin
}

setup_flight_plan_assistant() {
    local choice
    while true; do
        title "Fortify Flight Plan"
        printf '\nPurpose\n  Select the curated Fortify product-version bundle before deployment.\n'
        printf '\nCurrent status\n'
        setup_flight_plan_status
        cat <<'EOF'

Impact
  Flight Plans align SSC, ScanCentral, LIM, and DAST versions. Database versions
  stay separate because database rollback and app rollback carry different risks.

Options
  1. Select a Fortify Flight Plan
  2. Compare .env to selected Flight Plan
  3. Preview staged setup changes

  b. Back
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) flight_plan_select_menu SETUP_PENDING_UPDATES ;;
            2) flight_plan_show_comparison "$(setup_flight_plan_value)"; press_any ;;
            3) [ "${#SETUP_PENDING_UPDATES[@]}" -gt 0 ] && env_preview_changes "${SETUP_PENDING_UPDATES[@]}" || note "No pending setup changes."; press_any ;;
            [Bb]|"") return 0 ;;
            *) error "Invalid Flight Plan action"; sleep 1 ;;
        esac
    done
}

setup_tls_mode_label() {
    case "$(setup_pending_tls_mode)" in
        byo) printf '%s
' "bring your own certificate" ;;
        *) printf '%s
' "mkcert generated certificates" ;;
    esac
}

setup_byo_tls_validate_pending() {
    local saved_mode="${FORTIFY_TLS_MODE:-}" saved_cert="${FORTIFY_BYO_TLS_CERT:-}" saved_key="${FORTIFY_BYO_TLS_KEY:-}" saved_ca="${FORTIFY_BYO_TLS_CA_CERT:-}" rc=0
    FORTIFY_TLS_MODE="$(setup_pending_tls_mode)"
    FORTIFY_BYO_TLS_CERT="$(setup_pending_byo_tls_cert)"
    FORTIFY_BYO_TLS_KEY="$(setup_pending_byo_tls_key)"
    FORTIFY_BYO_TLS_CA_CERT="$(setup_pending_byo_tls_ca_cert)"
    export FORTIFY_TLS_MODE FORTIFY_BYO_TLS_CERT FORTIFY_BYO_TLS_KEY FORTIFY_BYO_TLS_CA_CERT
    fortify_tls_validate_byo_inputs || rc=$?
    FORTIFY_TLS_MODE="$saved_mode"
    FORTIFY_BYO_TLS_CERT="$saved_cert"
    FORTIFY_BYO_TLS_KEY="$saved_key"
    FORTIFY_BYO_TLS_CA_CERT="$saved_ca"
    export FORTIFY_TLS_MODE FORTIFY_BYO_TLS_CERT FORTIFY_BYO_TLS_KEY FORTIFY_BYO_TLS_CA_CERT
    return "$rc"
}

setup_byo_tls_stage() {
    local cert="$1" key="$2" ca="$3" resolved_cert resolved_key resolved_ca
    [ -n "$cert" ] || { error "Certificate path is required."; return 1; }
    [ -n "$key" ] || { error "Private key path is required."; return 1; }
    [ -n "$ca" ] || { error "CA/chain certificate path is required."; return 1; }
    resolved_cert="$(realpath -- "$cert")" || { error "Could not resolve certificate path."; return 1; }
    resolved_key="$(realpath -- "$key")" || { error "Could not resolve private key path."; return 1; }
    resolved_ca="$(realpath -- "$ca")" || { error "Could not resolve CA/chain path."; return 1; }
    setup_pending_set FORTIFY_TLS_MODE byo
    setup_pending_set FORTIFY_BYO_TLS_CERT "$resolved_cert"
    setup_pending_set FORTIFY_BYO_TLS_KEY "$resolved_key"
    setup_pending_set FORTIFY_BYO_TLS_CA_CERT "$resolved_ca"
    if ! setup_byo_tls_validate_pending; then
        setup_pending_unset FORTIFY_TLS_MODE
        setup_pending_unset FORTIFY_BYO_TLS_CERT
        setup_pending_unset FORTIFY_BYO_TLS_KEY
        setup_pending_unset FORTIFY_BYO_TLS_CA_CERT
        error "BYO TLS inputs did not validate. Nothing was applied yet."
        return 1
    fi
    note "BYO TLS certificate, key, and CA chain staged. Private key contents were not printed or copied."
}

setup_tls_status() {
    printf '
Purpose
  TLS secures lab URLs and feeds Java/fcli trust artifacts used by Fortify components.
'
    printf '
Current configuration
'
    printf '  TLS mode:        %s
' "$(setup_tls_mode_label)"
    printf '  Server cert:     %s
' "${SERVER_CERT:-$FORTIFY_HOME_K8S/certs/server.crt}"
    printf '  Server key:      %s
' "${SERVER_KEY:-$FORTIFY_HOME_K8S/certs/server.key}"
    printf '  JVM truststore:  %s
' "${TRUSTSTORE:-$FORTIFY_HOME_K8S/certs/truststore}"
    if [ "$(setup_pending_tls_mode)" = byo ]; then
        printf '  BYO cert:        %s
' "$(setup_pending_byo_tls_cert)"
        printf '  BYO key:         %s
' "$(setup_pending_byo_tls_key)"
        printf '  BYO CA/chain:    %s
' "$(setup_pending_byo_tls_ca_cert)"
    fi
    printf '
Verification
'
    certs_ready && printf '  %s Generated TLS artifacts are ready
' "$OK_MARK" || printf '  %s Generated TLS artifacts need generation
' "$WARN_MARK"
    if [ "$(setup_pending_tls_mode)" = byo ]; then
        setup_byo_tls_validate_pending && printf '  %s BYO TLS inputs validate for configured lab hostnames
' "$OK_MARK" || printf '  %s BYO TLS inputs need attention
' "$WARN_MARK"
    fi
    setup_root_ca_exported && printf '  %s Public root CA is exported
' "$OK_MARK" || printf '  %s Public root CA is not exported
' "$WARN_MARK"
    setup_fcli_trust_ready && printf '  %s fcli trust material is available
' "$OK_MARK" || printf '  %s fcli trust is not configured
' "$WARN_MARK"
    printf '
Impact
'
    printf '  Browser trust is client-side; every client must trust the issuing CA.
'
    printf '  After TLS changes, regenerate TLS artifacts and rerun Kubernetes secrets if deployments already exist.
'
    printf '
Recommended next action
'
    if [ "$(setup_pending_tls_mode)" = byo ]; then
        printf '  Generate TLS artifacts after applying BYO paths, then refresh Kubernetes secrets.
'
    else
        printf '  Use mkcert for local labs, or choose BYO if your organization manages certificates.
'
    fi
}

setup_tls_assistant() {
    local choice cert key ca
    while true; do
        title "TLS certificates and trust"
        setup_tls_status
        wizard_vertical_footer "TLS actions"             "1. Use mkcert-generated lab certificates"             "2. Bring your own certificate and key"             "3. Generate/regenerate TLS artifacts now"             "4. Stage root CA export"             "5. Stage fcli trust configuration"             "b. Back"
        echo
        ask choice "Select:"
        case "$choice" in
            1)
                setup_pending_set FORTIFY_TLS_MODE mkcert
                setup_pending_set FORTIFY_BYO_TLS_CERT ""
                setup_pending_set FORTIFY_BYO_TLS_KEY ""
                setup_pending_set FORTIFY_BYO_TLS_CA_CERT ""
                note "mkcert TLS mode staged."
                ;;
            2)
                ask cert "Certificate or full chain PEM path:"
                ask key "Private key PEM path:"
                ask ca "CA or issuer chain PEM path:"
                setup_byo_tls_stage "$cert" "$key" "$ca"
                ;;
            3) run_deployment_operation certs ;;
            4) setup_pending_action_add export-root-ca; note "Root CA export staged." ;;
            5) setup_pending_action_add configure-fcli-trust; note "fcli trust configuration staged." ;;
            [Bb]|"") return 0 ;;
            *) error "Invalid TLS action"; sleep 1 ;;
        esac
    done
}

setup_hosts_guidance() {
    local domain="$(setup_pending_domain_value)"
    [ -n "$domain" ] || domain="${DOMAIN:-fortifydemo.com}"
    cat <<EOF

Point these hostnames at the lab host IP from each client machine or DNS server:

  ssc.$domain
  lim.$domain
  sast.$domain
  dast.$domain
  dashboard.$domain
  juice-shop.$domain
  webgoat.$domain
  dvwa.$domain

The wizard never edits remote client host files.
EOF
}

known_issue_lines_from_text() {
    local text
    text=$(cat)
    grep -qi 'ImagePullBackOff\|Back-off pulling image\|pull access denied' <<<"$text" && printf 'Image pull failure: refresh Kubernetes registry credentials from a current Docker login.\n'
    grep -qi 'TRAEFIK DEFAULT CERT\|default cert' <<<"$text" && printf 'Traefik default certificate: verify ingress host, TLS secret, and regenerated lab certificates.\n'
    grep -qi 'RFC 1123\|placeholder-like value\|LIM_URL\|SCSAST_CTRL_URL' <<<"$text" && printf 'Invalid host or placeholder configuration: repair derived host and URL values from DOMAIN.\n'
    grep -qi 'Table .* already exists.*Failed to upgrade server\|MY-013380' <<<"$text" && printf 'MySQL upgrade failure: stale persistent data may need a data reset before redeploying MySQL.\n'
    grep -qi 'unbound immediate PersistentVolumeClaims\|FailedScheduling.*PersistentVolumeClaims' <<<"$text" && printf 'PVC scheduling issue: verify storage class, bound PVCs, and node capacity.\n'
    grep -qi 'Insufficient memory' <<<"$text" && printf 'Insufficient memory: increase lab host memory or deploy a smaller profile.\n'
    grep -qi 'SAST sensor.*complete.*does not advance\|Ready for work' <<<"$text" && printf 'SAST sensor readiness mismatch: verify the sensor StatefulSet, not only the controller pod.\n'
    return 0
}

known_issues_screen() {
    local findings
    title "Known issues detector"
    cat <<'EOF'
Paste Kubernetes events, pod logs, or wizard output. End input with Ctrl-D.
Secrets should be removed before pasting.

EOF
    findings=$(known_issue_lines_from_text || true)
    section "Findings"
    [ -n "$findings" ] && printf '%s\n' "$findings" | awk '{ printf "  - %s\n", $0 }' || printf '  No known issue pattern matched. Use diagnostics for live evidence.\n'
    press_any
}

setup_apply_pending_action() {
    case "$1" in
        refresh-registry) refresh_registry_credentials ;;
        export-root-ca) mkcert_root_ca_export ;;
        configure-fcli-trust) fcli_configure_lab_trust ;;
        *) return 0 ;;
    esac
}

setup_review_pending() {
    section "Pending .env changes"
    [ "${#SETUP_PENDING_UPDATES[@]}" -gt 0 ] && env_preview_changes "${SETUP_PENDING_UPDATES[@]}" || printf '  No .env changes staged.\n'
    section "Pending setup actions"
    [ "${#SETUP_PENDING_ACTIONS[@]}" -gt 0 ] && printf '  - %s\n' "${SETUP_PENDING_ACTIONS[@]}" || printf '  No setup actions staged.\n'
}

setup_apply_pending() {
    local action rc=0
    setup_review_pending
    echo
    confirm "Apply Guided Setup changes now?" || { note "Setup changes cancelled; nothing was applied."; return 1; }
    if [ "${#SETUP_PENDING_UPDATES[@]}" -gt 0 ]; then
        env_apply_updates guided-setup "${SETUP_PENDING_UPDATES[@]}" || return 1
        SETUP_PENDING_UPDATES=()
    fi
    for action in "${SETUP_PENDING_ACTIONS[@]}"; do
        setup_apply_pending_action "$action" || rc=$?
    done
    SETUP_PENDING_ACTIONS=()
    [ "$rc" -eq 0 ] && note "Guided Setup changes applied."
    return "$rc"
}

setup_guidance_block() {
    local purpose="$1" current="$2" impact="$3" next="$4"
    printf '\nPurpose\n  %s\n' "$purpose"
    printf '\nCurrent status\n%s\n' "$current"
    printf '\nImpact\n  %s\n' "$impact"
    printf '\nRecommended next action\n  %s\n' "$next"
}

setup_welcome_status() {
    cat <<EOF
  Guided Setup prepares configuration and readiness before deployment.
  Changes are staged until final review, so you can inspect everything before writing .env updates or running setup actions.
EOF
}

setup_identity_status() {
    printf '  Current domain:  %s\n' "${DOMAIN:-<unset>}"
    printf '  Proposed domain: %s\n' "$(setup_pending_domain_value)"
    printf '  Namespace:       %s\n' "$(env_pending_value NAMESPACE "${NAMESPACE:-fortify}" "${SETUP_PENDING_UPDATES[@]}")"
}

setup_license_status() {
    printf '  License status:  %s\n' "$(status_license)"
    printf '  Current input:   %s\n' "$(fortifylab_license_input_path)"
    printf '  Pending input:   %s\n' "$(setup_pending_license_value)"
}

setup_fcli_status() {
    setup_fcli_trust_ready && printf '  fcli truststore: ready\n' || printf '  fcli truststore: needs configuration\n'
    printf '  Truststore path: %s\n' "${FCLI_TRUSTSTORE:-${TRUSTSTORE:-$FORTIFY_HOME_K8S/certs/truststore}}"
}

guided_setup_step_screen() {
    local step="$1"
    title "Guided Setup - Step $((step + 1)) of ${#SETUP_STEP_LABEL[@]}"
    section "${SETUP_STEP_LABEL[$step]}"
    case "$step" in
        0)
            setup_guidance_block \
                "Orient the setup flow before changing configuration." \
                "$(setup_welcome_status)" \
                "This step does not change files or the cluster; it explains how staged setup works." \
                "Continue when you are ready to review the configurable setup sections."
            ;;
        1)
            setup_guidance_block \
                "Define the lab identity that drives hostnames, URLs, ingress hosts, and generated certificates." \
                "$(setup_identity_status)" \
                "Incorrect domain values lead to invalid ingress rules, TLS mismatches, browser warnings, or services opening at the wrong URL." \
                "Edit when the base domain should change; otherwise continue."
            ;;
        2)
            printf '\nPurpose\n  Choose which Fortify Lab components this environment should deploy and monitor.\n'
            printf '\nCurrent profile\n'
            setup_profile_preview "$(setup_profile_value)"
            printf '\nImpact\n  The profile controls guided deployment steps, readiness expectations, and which components are considered in lifecycle status.\n'
            printf '\nRecommended next action\n  Use Full lab for broad demos, or choose a smaller profile to save memory and deployment time.\n'
            ;;
        3)
            setup_guidance_block \
                "Select the Fortify product-version bundle used by deployment menus and diagnostics." \
                "$(setup_flight_plan_status)" \
                "A mismatched plan can deploy mixed Fortify versions and make troubleshooting harder. Database versions remain separately controlled." \
                "Use the recommended Flight Plan unless you are testing a specific Fortify release family."
            ;;
        4)
            setup_guidance_block \
                "Point the lab at a readable Fortify license file without printing license contents." \
                "$(setup_license_status)" \
                "A missing or unreadable license blocks complete Kubernetes secret creation and prevents licensed Fortify services from starting correctly." \
                "Edit to choose or import a license file before deployment."
            ;;
        5)
            printf '\nPurpose\n  Prepare Docker Hub credentials and the Kubernetes image pull secret used for Fortify images.\n'
            printf '\nCurrent status\n'
            setup_registry_status
            printf '\nImpact\n  If Docker credentials are stale or the Kubernetes regcred secret is missing, pods can fail with ImagePullBackOff even when manual docker pull works.\n'
            printf '\nRecommended next action\n  Run Docker login if needed, then stage a Kubernetes registry secret refresh after cluster access is ready.\n'
            ;;
        6) setup_tls_status ;;
        7)
            printf '\nPurpose\n  Show the hostnames clients must resolve to reach Fortify Lab services on the LAN.\n'
            printf '\nCurrent guidance\n'
            setup_hosts_guidance
            printf '\nImpact\n  DNS or hosts-file drift causes browsers and fcli to hit the wrong endpoint, Traefik default routes, or certificate names that do not match.\n'
            printf '\nRecommended next action\n  Add these names to DNS or each client hosts file, then test from the client machine.\n'
            ;;
        8)
            setup_guidance_block \
                "Prepare fcli to trust the lab certificate chain for local SSC and ScanCentral runbooks." \
                "$(setup_fcli_status)" \
                "Without fcli trust, browser access may work while fcli login fails with PKIX certificate validation errors." \
                "Stage fcli trust configuration after TLS artifacts exist, or continue if your shell already has the truststore configured."
            ;;
        9)
            printf '\nPurpose\n  Review staged .env changes and setup actions before anything is applied.\n'
            printf '\nCurrent status\n'
            setup_readiness_items
            setup_review_pending
            printf '\nImpact\n  Applying writes the staged configuration backup and may run selected setup actions such as registry, root CA, or fcli trust updates.\n'
            printf '\nRecommended next action\n  Continue to apply, or go back to adjust any section first.\n'
            ;;
    esac
}

guided_setup_edit_step() {
    local step="$1" value profile update
    case "$step" in
        1)
            ask value "New base domain, for example fortifydemo.com:"
            [ -n "$value" ] || return 0
            value=${value,,}
            env_valid_domain "$value" || { error "Use a lowercase DNS-style domain such as fortifydemo.com or lab.example.internal."; return 1; }
            while IFS= read -r update; do setup_pending_set "${update%%=*}" "${update#*=}"; done < <(domain_url_updates "$value")
            note "Domain and derived URL changes staged."
            ;;
        2)
            printf '\n  1. SSC only\n  2. SAST standalone\n  3. SAST full with SSC\n  4. DAST full\n  5. Full lab\n  6. Sample applications only\n'
            ask value "Select profile:"
            case "$value" in 1) profile=ssc_only ;; 2) profile=sast_standalone ;; 3) profile=sast_full ;; 4) profile=dast_full ;; 5|"") profile=full_lab ;; 6) profile=sample_apps ;; *) error "Invalid profile selection"; return 1 ;; esac
            setup_pending_set FORTIFY_DEPLOYMENT_PROFILE "$profile"
            setup_pending_set FORTIFY_DEPLOYMENT_COMPONENTS ""
            note "Deployment profile staged: $(guided_profile_label "$profile")"
            ;;
        3) setup_flight_plan_assistant ;;
        4) setup_license_assistant ;;
        5)
            wizard_vertical_footer "Registry actions" "1. Run Docker login" "2. Stage Kubernetes registry secret refresh" "b. Back"
            ask value "Select:"
            case "$value" in 1) setup_registry_login ;; 2) setup_pending_action_add refresh-registry; note "Registry secret refresh staged." ;; [Bb]|"") return 0 ;; *) error "Invalid registry action"; return 1 ;; esac
            ;;
        6) setup_tls_assistant ;;
        7) setup_hosts_guidance; press_any ;;
        8) setup_pending_action_add configure-fcli-trust; note "fcli trust configuration staged." ;;
        9) setup_apply_pending ;;
        *) note "Nothing to edit on this step." ;;
    esac
}

guided_setup_menu() {
    local step=0 choice
    SETUP_PENDING_UPDATES=()
    SETUP_PENDING_ACTIONS=()
    while true; do
        guided_setup_step_screen "$step"
        guided_setup_footer "$step"
        echo
        ask choice "Select:"
        case "$choice" in
            [Ee]) guided_setup_edit_step "$step"; press_any ;;
            [Cc]|"") [ "$step" -lt $((${#SETUP_STEP_LABEL[@]} - 1)) ] && step=$((step + 1)) || { setup_apply_pending; press_any; return $?; } ;;
            [Ss]) [ "$step" -lt $((${#SETUP_STEP_LABEL[@]} - 1)) ] && step=$((step + 1)) ;;
            [Bb]) [ "$step" -gt 0 ] && step=$((step - 1)) || return 0 ;;
            [Hh]) help_show_topic "$(guided_setup_help_topic "$step")" ;;
            [Qq]) note "Guided Setup cancelled; no staged changes were applied."; return 130 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

setup_menu() {
    local choice
    while true; do
        title "Setup and readiness"
        printf '\nSetup readiness: %s\n' "$(setup_readiness_score)"
        cat <<'EOF'

  1. Guided setup
  2. Setup readiness summary
  3. Deployment profile preview
  4. Registry credentials
  5. TLS and trust status
  6. Known issues detector

  r. Return
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) guided_setup_menu ;;
            2) setup_readiness_summary; press_any ;;
            3) title "Deployment profile preview"; setup_profile_preview "$(setup_profile_value)"; press_any ;;
            4) title "Registry credentials"; setup_registry_status; press_any ;;
            5) title "TLS and trust status"; setup_tls_status; press_any ;;
            6) known_issues_screen ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

lab_reset_tier_label() {
    case "$1" in soft) printf '%s\n' "Soft reset" ;; data) printf '%s\n' "Data reset" ;; full) printf '%s\n' "Full reset" ;; factory) printf '%s\n' "Factory reset" ;; *) return 1 ;; esac
}

lab_reset_confirmation_phrase() {
    case "$1" in soft) printf '%s\n' "RESET SOFT" ;; data) printf '%s\n' "RESET DATA" ;; full) printf '%s\n' "RESET FULL" ;; factory) printf '%s\n' "RESET FACTORY" ;; *) return 1 ;; esac
}

lab_reset_preview() {
    local tier="$1"
    section "$(lab_reset_tier_label "$tier") preview"
    case "$tier" in
        soft) printf '  - Stop all lab workloads.\n  - Preserve PVC data, .env, secrets, and certificates.\n' ;;
        data) printf '  - Destroy all application deployments and PVC-backed data using component destroy scripts.\n  - Preserve .env and generated certificates.\n' ;;
        full) printf '  - Run data reset.\n  - Remove generated Kubernetes secrets and lab TLS artifacts.\n  - Preserve .env after creating a backup.\n  - Clear the saved lab-use acknowledgement after reset succeeds.\n' ;;
        factory) printf '  - Run full reset.\n  - Restore .env from .env.example after backing up current .env.\n  - Clear wizard rollback marker and saved lab-use acknowledgement after reset succeeds.\n' ;;
    esac
}

lab_reset_execute() {
    local tier="$1" expected confirmation
    expected=$(lab_reset_confirmation_phrase "$tier") || return 1
    fortify_lab_show_action_warning destructive
    lab_reset_preview "$tier"
    printf '\nType %s to continue: ' "$expected"
    IFS= read -r confirmation
    if [ "$confirmation" != "$expected" ]; then
        note "Reset cancelled."
        wizard_log_event "action=lab_reset tier=$tier state=cancelled"
        return 1
    fi
    wizard_log_event "action=lab_reset tier=$tier state=started"
    case "$tier" in
        soft) lab_shutdown_deployments all ;;
        data) lab_destroy_deployments all ;;
        full) env_prepare_backup reset-full || return 1; lab_destroy_deployments all || return $?; rm -f "$FORTIFY_HOME_K8S/certs/server.crt" "$FORTIFY_HOME_K8S/certs/server.key" "$FORTIFY_HOME_K8S/certs/rootCA.pem" "$FORTIFY_HOME_K8S/certs/truststore" 2>/dev/null || true; fortify_lab_reset_acknowledgement || return 1 ;;
        factory) env_prepare_backup reset-factory || return 1; lab_destroy_deployments all || return $?; [ -s "$ENV_EXAMPLE" ] && cp "$ENV_EXAMPLE" "$ENV_FILE"; rm -f "$FORTIFY_HOME_K8S/.env.rollback" 2>/dev/null || true; fortify_lab_reset_acknowledgement || return 1 ;;
    esac
    wizard_log_event "action=lab_reset tier=$tier state=complete"
    note "Reset complete. Recommended next step: Guided setup."
}

lab_reset_menu() {
    local choice tier
    while true; do
        title "Complete lab reset"
        cat <<'EOF'

  1. Soft reset       Stop workloads; preserve data and config
  2. Data reset       Destroy deployments and PVC-backed app data
  3. Full reset       Data reset plus generated secrets/certs cleanup
  4. Factory reset    Full reset plus restore .env from .env.example

  p. Preview all reset tiers
  r. Return
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) tier=soft; lab_reset_execute "$tier"; press_any ;;
            2) tier=data; lab_reset_execute "$tier"; press_any ;;
            3) tier=full; lab_reset_execute "$tier"; press_any ;;
            4) tier=factory; lab_reset_execute "$tier"; press_any ;;
            [Pp]) for tier in soft data full factory; do lab_reset_preview "$tier"; done; press_any ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}
