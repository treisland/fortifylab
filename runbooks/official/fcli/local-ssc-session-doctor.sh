#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC session doctor
# description: Checks local fcli readiness, SSC session visibility, and a small authenticated SSC query without printing tokens or session files.
# domain: Local lab: SSC
# category: FCLI
# risk: low
# order: 35
# requires: bash
# params:
#   - name: session_name
#     description: fcli SSC session name to inspect.
#     default: fortifylab
#     required: true
#   - name: token_env_var
#     description: Optional environment variable expected to contain the SSC token. Only the variable name and set/unset status are printed.
#     default: FCLI_DEFAULT_SSC_TOKEN
#     required: false
#   - name: max_appversions
#     description: Maximum application versions to fetch for the authenticated smoke check.
#     default: 3
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

is_positive_integer() {
    [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

print_check() {
    local status="$1" message="$2"
    printf '  %-7s %s
' "$status" "$message"
}

run_help_check() {
    local label="$1"
    shift
    if "$fcli_cmd" "$@" --help >/dev/null 2>&1; then
        print_check "ok" "$label is available"
    else
        print_check "warn" "$label was not available in this fcli build"
    fi
}

: "${SESSION_NAME:?SESSION_NAME is required.}"

if ! is_positive_integer "${MAX_APPVERSIONS:-}"; then
    echo "MAX_APPVERSIONS must be a positive integer."
    exit 1
fi

fcli_cmd="$(resolve_fcli_bin || true)"

echo "Local SSC session doctor"
echo "  SSC session:             $SESSION_NAME"
echo "  Token variable:          ${TOKEN_ENV_VAR:-<not checked>}"
echo

if [ -z "$fcli_cmd" ]; then
    print_check "fail" "fcli not found. Install it from the wizard's Tools and FCLI readiness screen or set FCLI_BIN."
    exit 1
fi

echo "fcli runtime"
echo "  Binary:                  $fcli_cmd"
printf '  Version:                 '
"$fcli_cmd" --version 2>/dev/null || echo "<unable to read>"
run_help_check "ssc session list" ssc session list
run_help_check "ssc appversion list" ssc appversion list
echo

echo "Token environment"
if [ -n "${TOKEN_ENV_VAR:-}" ]; then
    if [ -n "${!TOKEN_ENV_VAR:-}" ]; then
        print_check "ok" "$TOKEN_ENV_VAR is set"
    else
        print_check "warn" "$TOKEN_ENV_VAR is not set; existing sessions may still work"
    fi
else
    print_check "skip" "No token environment variable name was provided"
fi
echo

echo "SSC sessions"
if "$fcli_cmd" ssc session list -o table 2>/dev/null; then
    print_check "ok" "Session list command completed"
else
    print_check "warn" "Unable to list SSC sessions; check fcli state permissions and login status"
fi
echo

echo "Authenticated SSC smoke check"
if "$fcli_cmd" ssc appversion list --ssc-session "$SESSION_NAME" --fetch "$MAX_APPVERSIONS" -o table 2>/dev/null; then
    print_check "ok" "Session '$SESSION_NAME' can query SSC application versions"
else
    print_check "fail" "Session '$SESSION_NAME' could not query SSC. Re-run the login discovery runbook or check SSC readiness."
    exit 2
fi
echo

echo "No token values, session file contents, or fcli state files were printed."
