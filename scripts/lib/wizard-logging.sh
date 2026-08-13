#!/bin/bash
# Private, sanitized self-logging helpers for the Fortify Lab wizard.
# Source this module from interactive wizard code; it performs no logging on load.

FORTIFY_WIZARD_LOG_NAME="${FORTIFY_WIZARD_LOG_NAME:-wizard.log}"
FORTIFY_WIZARD_LOG_MAX_BYTES="${FORTIFY_WIZARD_LOG_MAX_BYTES:-1048576}"
FORTIFY_WIZARD_LOG_ROTATIONS="${FORTIFY_WIZARD_LOG_ROTATIONS:-5}"
FORTIFY_WIZARD_LOG_TAIL_LINES="${FORTIFY_WIZARD_LOG_TAIL_LINES:-80}"

fortify_wizard_log_error() {
    printf 'ERROR: %s\n' "$*" >&2
}

fortify_wizard_log_require_integer() {
    local name="$1" value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        fortify_wizard_log_error "$name must be a non-negative integer."
        return 1
    fi
}

fortify_wizard_log_state_dir() {
    local state_root
    if [ -n "${FORTIFY_WIZARD_LOG_DIR:-}" ]; then
        case "$FORTIFY_WIZARD_LOG_DIR" in
            /*) printf '%s\n' "$FORTIFY_WIZARD_LOG_DIR" ;;
            *)
                fortify_wizard_log_error "FORTIFY_WIZARD_LOG_DIR must be an absolute path."
                return 1
                ;;
        esac
        return 0
    fi

    if [ -n "${XDG_STATE_HOME:-}" ]; then
        state_root="$XDG_STATE_HOME"
    else
        state_root="${HOME:?HOME is required}/.local/state"
    fi
    case "$state_root" in
        /*) printf '%s/fortify-lab\n' "$state_root" ;;
        *)
            fortify_wizard_log_error "The user state directory must be an absolute path."
            return 1
            ;;
    esac
}

fortify_wizard_log_file() {
    local state_dir
    if [ -n "${FORTIFY_WIZARD_LOG_FILE:-}" ]; then
        case "$FORTIFY_WIZARD_LOG_FILE" in
            /*) printf '%s\n' "$FORTIFY_WIZARD_LOG_FILE" ;;
            *)
                fortify_wizard_log_error "FORTIFY_WIZARD_LOG_FILE must be an absolute path."
                return 1
                ;;
        esac
        return 0
    fi

    state_dir="$(fortify_wizard_log_state_dir)" || return 1
    printf '%s/%s\n' "$state_dir" "$FORTIFY_WIZARD_LOG_NAME"
}

fortify_wizard_log_prepare() {
    local log_file log_dir
    fortify_wizard_log_require_integer FORTIFY_WIZARD_LOG_MAX_BYTES "$FORTIFY_WIZARD_LOG_MAX_BYTES" || return 1
    fortify_wizard_log_require_integer FORTIFY_WIZARD_LOG_ROTATIONS "$FORTIFY_WIZARD_LOG_ROTATIONS" || return 1
    log_file="$(fortify_wizard_log_file)" || return 1
    log_dir="$(dirname -- "$log_file")"

    if ! mkdir -p -- "$log_dir"; then
        fortify_wizard_log_error "Unable to create the wizard log directory."
        return 1
    fi
    chmod 700 -- "$log_dir" 2>/dev/null || true
    if [ ! -e "$log_file" ] && ! : >"$log_file"; then
        fortify_wizard_log_error "Unable to create the wizard log file."
        return 1
    fi
    chmod 600 -- "$log_file" 2>/dev/null || true
}

fortify_wizard_log_sanitize() {
    local text="$*"
    printf '%s\n' "$text" | sed -E \
        -e 's/[[:cntrl:]]+/ /g' \
        -e 's#(https?://[^:/[:space:]]+):[^@/[:space:]]+@#\1:[REDACTED]@#g' \
        -e 's/([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Pp][Aa][Ss][Ss]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Ll][Ii][Cc][Ee][Nn][Ss][Ee]|[Aa][Uu][Tt][Hh])([[:space:]_.-]*(=|:)[[:space:]]*)[^[:space:],;]+/\1\2[REDACTED]/g' \
        -e 's/(--?[A-Za-z0-9_-]*([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Ll][Ii][Cc][Ee][Nn][Ss][Ee]|[Aa][Uu][Tt][Hh])[A-Za-z0-9_-]*)(=|[[:space:]]+)[^[:space:],;]+/\1\3[REDACTED]/g'
}

fortify_wizard_log_rotate_if_needed() {
    local log_file size index previous
    fortify_wizard_log_prepare || return 1
    log_file="$(fortify_wizard_log_file)" || return 1
    [ "$FORTIFY_WIZARD_LOG_MAX_BYTES" -gt 0 ] || return 0
    size=$(wc -c <"$log_file" 2>/dev/null) || size=0
    [ "$size" -ge "$FORTIFY_WIZARD_LOG_MAX_BYTES" ] || return 0

    if [ "$FORTIFY_WIZARD_LOG_ROTATIONS" -eq 0 ]; then
        : >"$log_file"
        chmod 600 -- "$log_file" 2>/dev/null || true
        return 0
    fi

    index="$FORTIFY_WIZARD_LOG_ROTATIONS"
    while [ "$index" -gt 1 ]; do
        previous=$((index - 1))
        [ -e "${log_file}.${previous}" ] && mv -f -- "${log_file}.${previous}" "${log_file}.${index}"
        index="$previous"
    done
    mv -f -- "$log_file" "${log_file}.1"
    : >"$log_file"
    chmod 600 -- "$log_file" 2>/dev/null || true
}

fortify_wizard_log() {
    local level="${1:-INFO}" message timestamp log_file
    shift || true
    message="$(fortify_wizard_log_sanitize "$*")"
    fortify_wizard_log_rotate_if_needed || return 1
    log_file="$(fortify_wizard_log_file)" || return 1
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s [%s] %s\n' "$timestamp" "$level" "$message" >>"$log_file"
}

fortify_wizard_log_tail() {
    local lines="${1:-$FORTIFY_WIZARD_LOG_TAIL_LINES}" log_file
    fortify_wizard_log_require_integer lines "$lines" || return 1
    log_file="$(fortify_wizard_log_file)" || return 1
    [ -f "$log_file" ] || return 0
    tail -n "$lines" -- "$log_file"
}

fortify_wizard_log_view() {
    local lines="${1:-$FORTIFY_WIZARD_LOG_TAIL_LINES}"
    fortify_wizard_log_tail "$lines"
}
