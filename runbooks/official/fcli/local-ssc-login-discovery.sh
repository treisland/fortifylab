#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC login and discovery
# description: Logs in to the local SSC lab with a token from an environment variable, then lists basic SSC application-version context.
# domain: Local lab: SSC
# category: FCLI
# risk: medium
# order: 30
# requires: bash
# params:
#   - name: ssc_url
#     description: Local SSC URL. Defaults to SSC_URL from the FortifyLab environment.
#     defaultFromEnv: SSC_URL
#     required: true
#   - name: sc_sast_url
#     description: Local ScanCentral SAST Controller URL. Defaults to SCSAST_CTRL_URL when available.
#     defaultFromEnv: SCSAST_CTRL_URL
#     required: false
#   - name: session_name
#     description: fcli SSC session name to create or reuse.
#     default: fortifylab
#     required: true
#   - name: token_env_var
#     description: Environment variable containing the SSC token. The token value is never printed or passed as a command-line argument.
#     default: FCLI_DEFAULT_SSC_TOKEN
#     required: true
#   - name: max_appversions
#     description: Maximum application versions to list after login.
#     default: 10
#     required: true

set -euo pipefail

resolve_fcli_bin() {
    if [ -n "${FCLI_BIN:-}" ]; then
        printf '%s\n' "$FCLI_BIN"
        return 0
    fi
    if [ -n "${FORTIFY_FCLI_INSTALL_DIR:-}" ] && [ -x "${FORTIFY_FCLI_INSTALL_DIR}/fcli" ]; then
        printf '%s\n' "${FORTIFY_FCLI_INSTALL_DIR}/fcli"
        return 0
    fi
    command -v fcli 2>/dev/null || return 1
}

is_positive_integer() {
    [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

mask_url() {
    local value="$1"
    value="${value%%\?*}"
    printf '%s\n' "$value"
}

fcli_cmd="$(resolve_fcli_bin || true)"
[ -n "$fcli_cmd" ] || {
    echo "fcli not found. Install it from the wizard's Tools and FCLI readiness screen or set FCLI_BIN."
    exit 1
}

: "${SSC_URL:?SSC_URL is required. Set SSC_URL or pass the ssc_url parameter.}"
: "${SESSION_NAME:?SESSION_NAME is required.}"
: "${TOKEN_ENV_VAR:?TOKEN_ENV_VAR is required.}"

if ! is_positive_integer "${MAX_APPVERSIONS:-}"; then
    echo "MAX_APPVERSIONS must be a positive integer."
    exit 1
fi

token_value="${!TOKEN_ENV_VAR:-}"

echo "Local SSC fcli discovery"
echo "  SSC URL:                 $(mask_url "$SSC_URL")"
echo "  ScanCentral SAST URL:    ${SC_SAST_URL:-<not set; fcli may use SSC configuration>}"
echo "  SSC session:             $SESSION_NAME"
echo "  Token variable:          $TOKEN_ENV_VAR"
echo "  fcli binary:             $fcli_cmd"
echo

if [ -z "$token_value" ]; then
    echo "No token value found in $TOKEN_ENV_VAR."
    echo "Create or export an SSC token in a private shell, then rerun this runbook."
    echo
    echo "Safe command shape:"
    echo "  export $TOKEN_ENV_VAR='<SSC_TOKEN_VALUE>'"
    echo "  fcli ssc session login --url '$(mask_url "$SSC_URL")' --token '<redacted>' --ssc-session '$SESSION_NAME'"
    echo
    echo "This runbook intentionally does not accept token values as wizard parameters."
    exit 2
fi

login_cmd=("$fcli_cmd" ssc session login --url "$SSC_URL" --ssc-session "$SESSION_NAME")
if [ -n "${SC_SAST_URL:-}" ]; then
    login_cmd+=(--sc-sast-url "$SC_SAST_URL")
fi
echo "Logging in to local SSC with token from $TOKEN_ENV_VAR..."
FCLI_DEFAULT_SSC_TOKEN="$token_value" "${login_cmd[@]}" >/dev/null
echo "Login complete. Token values were not printed."
echo

echo "SSC session summary"
"$fcli_cmd" ssc session list -o table 2>/dev/null || {
    echo "  Session list was not available; continuing with application-version discovery."
}
echo

echo "SSC application versions (up to $MAX_APPVERSIONS)"
if ! "$fcli_cmd" ssc appversion list --ssc-session "$SESSION_NAME" --fetch "$MAX_APPVERSIONS" -o table 2>/dev/null; then
    echo "  Unable to list application versions. Check token permissions and SSC readiness."
fi
echo

echo "When finished, run:"
echo "  fcli ssc session logout --ssc-session '$SESSION_NAME'"
