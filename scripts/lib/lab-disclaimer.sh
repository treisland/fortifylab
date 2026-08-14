#!/usr/bin/env bash

# Lab-use acknowledgement contract for the Fortify lab wizard.
# This module stores no credentials and deliberately keeps its marker outside
# the repository. Callers should source it; it does not execute on its own.

FORTIFY_LAB_ACK_VERSION="1"

fortify_lab_version() {
    if [ -n "${FORTIFYLAB_VERSION:-}" ]; then
        printf '%s
' "$FORTIFYLAB_VERSION"
        return 0
    fi
    if command -v git >/dev/null 2>&1 && [ -n "${FORTIFY_HOME_K8S:-}" ]; then
        git -C "$FORTIFY_HOME_K8S" describe --tags --always --dirty 2>/dev/null && return 0
    fi
    printf '%s
' "unknown"
}

fortify_lab_terminal_columns() {
    if [ -n "${COLUMNS:-}" ] && [[ "$COLUMNS" =~ ^[0-9]+$ ]]; then
        printf '%s
' "$COLUMNS"
        return 0
    fi
    tput cols 2>/dev/null || printf '%s
' 80
}

fortify_lab_welcome_banner() {
    [ -n "${FORTIFY_NO_BANNER:-}" ] && return 0

    local version columns width title subtitle plain border_color reset_color title_color
    version="$(fortify_lab_version)"
    columns="$(fortify_lab_terminal_columns)"
    title="FortifyLab"
    subtitle="Ready-to-scan Fortify training lab"

    if [ -n "${NO_COLOR:-}" ] || [ "${columns:-80}" -lt 64 ]; then
        printf '%s %s
' "$title" "$version"
        printf '%s
' "$subtitle"
        return 0
    fi

    width=60
    border_color="${BLUE:-}"
    title_color="${BOLD:-}"
    reset_color="${RESET:-}"
    plain=$(printf '%*s' "$width" '')
    printf '%s╭%s╮%s
' "$border_color" "${plain// /─}" "$reset_color"
    printf '%s│%s %s%-32s%18s %s│%s
' "$border_color" "$reset_color" "$title_color" "$title" "$version" "$border_color" "$reset_color"
    printf '%s│%s %-58s %s│%s
' "$border_color" "$reset_color" "$subtitle" "$border_color" "$reset_color"
    printf '%s╰%s╯%s
' "$border_color" "${plain// /─}" "$reset_color"
}

fortify_lab_config_dir() {
    local config_root
    if [ -n "${XDG_CONFIG_HOME:-}" ]; then
        config_root="$XDG_CONFIG_HOME"
    else
        config_root="${HOME:?HOME is required}/.config"
    fi
    case "$config_root" in
        /*) printf '%s/fortify-lab\n' "$config_root" ;;
        *)
            printf '%s\n' "The user configuration directory must be an absolute path." >&2
            return 1
            ;;
    esac
}

fortify_lab_acknowledgement_file() {
    printf '%s/acknowledged-lab-use\n' "$(fortify_lab_config_dir)"
}

fortify_lab_is_acknowledged() {
    local marker
    marker="$(fortify_lab_acknowledgement_file)" || return 1
    [ -f "$marker" ] && [ "$(<"$marker")" = "version=$FORTIFY_LAB_ACK_VERSION" ]
}

fortify_lab_record_acknowledgement() {
    local config_dir marker temporary_marker
    config_dir="$(fortify_lab_config_dir)" || return 1
    marker="$(fortify_lab_acknowledgement_file)" || return 1

    if ! mkdir -p -- "$config_dir"; then
        printf '%s\n' "Unable to save the lab-use acknowledgement in the user configuration directory." >&2
        return 1
    fi
    chmod 700 -- "$config_dir" 2>/dev/null || true
    if ! temporary_marker="$(mktemp "$config_dir/.acknowledgement.XXXXXX")"; then
        printf '%s\n' "Unable to save the lab-use acknowledgement in the user configuration directory." >&2
        return 1
    fi
    chmod 600 -- "$temporary_marker" 2>/dev/null || true
    if ! printf 'version=%s\n' "$FORTIFY_LAB_ACK_VERSION" >"$temporary_marker"; then
        rm -f -- "$temporary_marker"
        printf '%s\n' "Unable to save the lab-use acknowledgement in the user configuration directory." >&2
        return 1
    fi
    if ! mv -f -- "$temporary_marker" "$marker"; then
        rm -f -- "$temporary_marker"
        printf '%s\n' "Unable to save the lab-use acknowledgement in the user configuration directory." >&2
        return 1
    fi
}

fortify_lab_reset_acknowledgement() {
    local marker
    marker="$(fortify_lab_acknowledgement_file)" || return 1
    if ! rm -f -- "$marker"; then
        printf '%s\n' "Unable to reset the lab-use acknowledgement." >&2
        return 1
    fi
    printf '%s\n' "Lab-use acknowledgement reset. It will be required on the next launch."
}

fortify_lab_show_notice() {
    fortify_lab_welcome_banner
    printf '\n'
    cat <<'NOTICE'
LAB / DEMO USE ONLY

The deployment architecture and automation in this repository are intended
only for evaluation, demonstrations, training, and isolated lab use. They are
not a production deployment architecture and do not provide production-grade
availability, security hardening, backup, disaster recovery, monitoring, or
support guarantees.

Do not use this lab for production workloads, regulated or business-critical
data, real credentials, customer data, production source code, or production
scan results. Restrict network exposure and follow applicable Fortify licensing
terms.

This limitation applies to this repository's architecture and automation. It
does not limit the production capabilities of Fortify products.
NOTICE
}

fortify_lab_menu_banner() {
    printf '%s\n' "Mode: LAB / DEMO ONLY — repository automation is not production supported"
}

fortify_lab_show_action_warning() {
    case "${1:-}" in
        admin-token)
            printf '%s\n' \
                "LAB WARNING: An administrator token grants full control of this lab cluster." \
                "Use a short-lived token only in the isolated lab; do not copy it into logs or configuration."
            ;;
        destructive)
            printf '%s\n' \
                "LAB WARNING: This action can remove lab workloads or data and may not be recoverable." \
                "Confirm the exact target and preserve any lab data you need before continuing."
            ;;
        *)
            printf '%s\n' "Unknown lab warning context." >&2
            return 2
            ;;
    esac
}

# Detect the documented opt-in for automation. The caller remains responsible
# for rejecting all unsupported command-line arguments.
fortify_lab_detect_accept_flag() {
    local argument
    FORTIFY_LAB_NONINTERACTIVE_ACCEPTED=0
    for argument in "$@"; do
        if [ "$argument" = "--accept-lab-use" ]; then
            FORTIFY_LAB_NONINTERACTIVE_ACCEPTED=1
        fi
    done
}

fortify_lab_require_acknowledgement() {
    local response
    if fortify_lab_is_acknowledged; then
        return 0
    fi

    fortify_lab_show_notice
    if [ "${FORTIFY_LAB_NONINTERACTIVE_ACCEPTED:-0}" = "1" ]; then
        fortify_lab_record_acknowledgement || return 1
        printf '%s\n' "Lab/demo use acknowledged through the explicit noninteractive option."
        return 0
    fi

    printf '\nType LAB to acknowledge these limits and continue: '
    if ! IFS= read -r response; then
        printf '\n%s\n' "Lab-use acknowledgement was not received; stopping safely." >&2
        return 1
    fi
    if [ "$response" != "LAB" ]; then
        printf '%s\n' "Lab-use acknowledgement declined; stopping safely." >&2
        return 1
    fi
    fortify_lab_record_acknowledgement || return 1
    printf '%s\n' "Lab/demo use acknowledged."
}
