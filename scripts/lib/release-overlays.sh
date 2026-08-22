#!/usr/bin/env bash
# shellcheck shell=bash
# Release-aware deployment overlay helpers.
#
# Flight Plans select component versions. Release overlays are optional,
# repo-owner maintained snippets that adjust deployment behavior for a
# specific Flight Plan release without duplicating whole app scripts.
#
# Overlay contract:
#   - File path: apps/<app-id>/releases/<release>/overrides.sh
#   - App ids may include path separators, for example scdast/core.
#   - An overlay may append Helm arguments to RELEASE_OVERLAY_HELM_ARGS.
#   - Missing overlays are normal.
#   - Selected overlays must pass bash -n before they are sourced.

release_overlay_tool_path() {
    printf '%s/scripts/tools/flight-plans.py\n' "${FORTIFY_HOME_K8S:-$(pwd)}"
}

release_overlay_selected_plan() {
    if declare -F flight_plan_selected_id >/dev/null 2>&1; then
        flight_plan_selected_id
        return 0
    fi
    if [ -n "${FORTIFY_FLIGHT_PLAN:-}" ]; then
        printf '%s\n' "$FORTIFY_FLIGHT_PLAN"
        return 0
    fi
    python3 "$(release_overlay_tool_path)" default 2>/dev/null || printf '%s\n' fortify-26.2
}

release_overlay_selected_release() {
    local plan_id="${1:-$(release_overlay_selected_plan)}" release=""
    release=$(python3 "$(release_overlay_tool_path)" show "$plan_id" 2>/dev/null | awk -F: '/^Family:/ { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit }') || true
    if [[ "$release" =~ ^[0-9]{2,4}\.[0-9]+$ ]]; then
        printf '%s\n' "$release"
        return 0
    fi
    if [[ "$plan_id" =~ ^fortify-([0-9]{2,4}\.[0-9]+)$ ]]; then
        printf '%s\n' "${BASH_REMATCH[1]}"
        return 0
    fi
    return 1
}

release_overlay_path() {
    local app_id="$1" release="${2:-$(release_overlay_selected_release 2>/dev/null || true)}"
    [ -n "$release" ] || return 1
    printf '%s/apps/%s/releases/%s/overrides.sh\n' "${FORTIFY_HOME_K8S:-$(pwd)}" "$app_id" "$release"
}

release_overlay_log() {
    if declare -F wizard_log_event >/dev/null 2>&1; then
        wizard_log_event "$*"
    elif [ -n "${FORTIFYLAB_WIZARD_LOG:-}" ]; then
        printf '%s %s\n' "$(date -Is 2>/dev/null || date)" "$*" >>"$FORTIFYLAB_WIZARD_LOG" 2>/dev/null || true
    fi
}

release_overlay_status() {
    local app_id="$1" release path
    release=$(release_overlay_selected_release 2>/dev/null || true)
    if [ -z "$release" ]; then
        printf 'no-release\n'
        return 0
    fi
    path=$(release_overlay_path "$app_id" "$release") || { printf 'no-release\n'; return 0; }
    if [ ! -e "$path" ]; then
        printf 'not-found\n'
    elif [ ! -r "$path" ]; then
        printf 'unreadable\n'
    elif ! bash -n "$path" >/dev/null 2>&1; then
        printf 'syntax-error\n'
    else
        printf 'available\n'
    fi
}

release_overlay_status_line() {
    local app_id="$1" label="${2:-$1}" release path display_path status root
    root="${FORTIFY_HOME_K8S:-$(pwd)}"
    release=$(release_overlay_selected_release 2>/dev/null || true)
    if [ -z "$release" ]; then
        printf '  %-28s no release baseline selected\n' "$label"
        return 0
    fi
    path=$(release_overlay_path "$app_id" "$release") || path=""
    display_path="${path#$root/}"
    status=$(release_overlay_status "$app_id")
    case "$status" in
        available) printf '  %-28s %s\n' "$label" "$display_path" ;;
        not-found) printf '  %-28s none for release %s\n' "$label" "$release" ;;
        syntax-error) printf '  %-28s syntax error in %s\n' "$label" "$display_path" ;;
        unreadable) printf '  %-28s unreadable %s\n' "$label" "$display_path" ;;
        *) printf '  %-28s %s\n' "$label" "$status" ;;
    esac
}

release_overlay_default_app_ids() {
    printf '%s\n' ssc lim scsast scdast/core scdast/scanner
}

release_overlay_status_lines() {
    release_overlay_status_line ssc "SSC"
    release_overlay_status_line lim "LIM"
    release_overlay_status_line scsast "ScanCentral SAST"
    release_overlay_status_line scdast/core "ScanCentral DAST Core"
    release_overlay_status_line scdast/scanner "ScanCentral DAST Scanner"
}

release_overlay_validate_selected() {
    local app_id status failed=0
    if [ "$#" -eq 0 ]; then
        set -- $(release_overlay_default_app_ids)
    fi
    for app_id in "$@"; do
        status=$(release_overlay_status "$app_id")
        case "$status" in
            available|not-found|no-release) ;;
            *)
                release_overlay_status_line "$app_id" "$app_id" >&2
                failed=1
                ;;
        esac
    done
    return "$failed"
}

release_overlay_report() {
    local plan_id release
    plan_id="$(release_overlay_selected_plan)"
    release="$(release_overlay_selected_release "$plan_id" 2>/dev/null || true)"
    printf 'Selected Flight Plan: %s\n' "$plan_id"
    if [ -n "$release" ]; then
        printf 'Selected release overlay baseline: %s\n' "$release"
    else
        printf 'Selected release overlay baseline: unavailable\n'
    fi
    printf 'Release overlays:\n'
    release_overlay_status_lines
}

release_overlay_load() {
    local app_id="$1" release path status
    RELEASE_OVERLAY_HELM_ARGS=()
    export RELEASE_OVERLAY_APP_ID="$app_id"
    release=$(release_overlay_selected_release 2>/dev/null || true)
    export RELEASE_OVERLAY_RELEASE="$release"
    if [ -z "$release" ]; then
        RELEASE_OVERLAY_STATUS="no-release"
        release_overlay_log "overlay app=$app_id status=no-release"
        return 0
    fi
    path=$(release_overlay_path "$app_id" "$release") || return 0
    export RELEASE_OVERLAY_PATH="$path"
    status=$(release_overlay_status "$app_id")
    RELEASE_OVERLAY_STATUS="$status"
    case "$status" in
        not-found)
            release_overlay_log "overlay app=$app_id release=$release status=not-found"
            return 0
            ;;
        available)
            # shellcheck disable=SC1090
            source "$path"
            release_overlay_log "overlay app=$app_id release=$release path=$path status=loaded"
            return 0
            ;;
        *)
            printf 'ERROR: Release overlay for %s %s is %s: %s\n' "$app_id" "$release" "$status" "$path" >&2
            release_overlay_log "overlay app=$app_id release=$release path=$path status=$status"
            return 1
            ;;
    esac
}
