#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC logout and session cleanup
# description: Logs out a named local SSC fcli session and shows the remaining session summary without printing session files or secrets.
# domain: Local lab: SSC
# category: FCLI
# risk: medium
# order: 90
# requires: bash
# params:
#   - name: session_name
#     description: fcli SSC session name to log out.
#     default: fortifylab
#     required: true
#   - name: show_state_dirs
#     description: Print configured fcli state directory paths without reading their contents.
#     default: true
#     required: true

set -euo pipefail

resolve_fcli_bin() {
    if [ -n "${FCLI_BIN:-}" ]; then
        printf '%s
' "$FCLI_BIN"
        return 0
    fi
    if [ -n "${FORTIFY_FCLI_INSTALL_DIR:-}" ] && [ -x "${FORTIFY_FCLI_INSTALL_DIR}/fcli" ]; then
        printf '%s
' "${FORTIFY_FCLI_INSTALL_DIR}/fcli"
        return 0
    fi
    command -v fcli 2>/dev/null || return 1
}

print_path_value() {
    local label="$1" value="$2"
    if [ -n "$value" ]; then
        printf '  %-24s %s
' "$label:" "$value"
    else
        printf '  %-24s %s
' "$label:" "<default>"
    fi
}

print_sessions() {
    if ! "$fcli_cmd" ssc session list -o table 2>/dev/null; then
        echo "  No SSC session list was returned."
    fi
}

: "${SESSION_NAME:?SESSION_NAME is required.}"

fcli_cmd="$(resolve_fcli_bin || true)"
[ -n "$fcli_cmd" ] || {
    echo "fcli not found. Install it from the wizard's Tools and FCLI readiness screen or set FCLI_BIN."
    exit 1
}

echo "Local SSC logout and session cleanup"
echo "  SSC session:             $SESSION_NAME"
echo "  fcli binary:             $fcli_cmd"
echo

if [ "${SHOW_STATE_DIRS:-true}" = "true" ]; then
    echo "Configured fcli state paths"
    print_path_value "FCLI_USER_HOME" "${FCLI_USER_HOME:-}"
    print_path_value "FCLI_DATA_DIR" "${FCLI_DATA_DIR:-}"
    print_path_value "FCLI_STATE_DIR" "${FCLI_STATE_DIR:-}"
    print_path_value "FCLI_CONFIG_DIR" "${FCLI_CONFIG_DIR:-}"
    echo "  Note: paths only; this runbook does not read or print session file contents."
    echo
fi

echo "Sessions before logout"
print_sessions
echo

if ! "$fcli_cmd" ssc session logout --help >/dev/null 2>&1; then
    echo "This fcli build does not expose 'ssc session logout' as expected for v3."
    exit 2
fi

echo "Logging out SSC session '$SESSION_NAME'..."
if "$fcli_cmd" ssc session logout --ssc-session "$SESSION_NAME" >/dev/null 2>&1; then
    echo "Logout command completed."
else
    echo "Logout command did not complete. The session may already be absent, or fcli state may be unavailable."
fi
echo

echo "Sessions after logout"
print_sessions
echo

echo "Cleanup complete. No token values, session file contents, or fcli state files were printed."
