#!/usr/bin/env bash
# shellcheck shell=bash
# Module: operations/environment-editor
# Responsibility: Edit, validate, diagnose, and repair deployment configuration.
# Requires: ENV_FILE; APP_* registries; env_section_keys; environment-store exports;
#           deployment-version exports; app_status; UI helpers; python3.
# Exports: env_section_*, env_guided_section_editor, env_valid_domain,
#          env_url_host, env_expected_*, env_placeholder_like, env_config_*,
#          deployment_config_guard, app_start_config_guard, env_repair_domain_urls,
#          env_diagnostics, domain_url_updates, domain_url_assistant.
# Side effects: May update ENV_FILE; validation and diagnostic functions are read-only.
# Interactive: editor, repair, diagnostics, and assistant entry points prompt.

if [[ -n "${FORTIFYLAB_WIZARD_ENVIRONMENT_EDITOR_LOADED:-}" ]]; then
    return 0
fi
FORTIFYLAB_WIZARD_ENVIRONMENT_EDITOR_LOADED=1

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
        release_overlay_report
        release_overlay_validate_selected || rc=$?
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
    release_overlay_report
    release_overlay_validate_selected || return $?
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

