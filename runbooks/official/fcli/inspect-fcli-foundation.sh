#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Inspect fcli version and sessions
# description: Shows the local fcli binary, version, data directories, and SSC session summary without printing session files or secrets.
# domain: fcli basics
# category: FCLI
# risk: low
# order: 20
# requires: bash
# params:
#   - name: fcli_bin
#     description: fcli command or absolute path. Defaults to FCLI_BIN, then FORTIFY_FCLI_INSTALL_DIR/fcli, then PATH.
#     defaultFromEnv: FCLI_BIN
#     required: false

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

print_path_value() {
    local label="$1" value="$2"
    if [ -n "$value" ]; then
        printf '  %-24s %s\n' "$label:" "$value"
    else
        printf '  %-24s %s\n' "$label:" "<default>"
    fi
}

fcli_cmd="$(resolve_fcli_bin || true)"

echo "fcli foundation"
if [ -z "$fcli_cmd" ]; then
    echo "  Status:                  fcli not found"
    echo "  Suggested install dir:   ${FORTIFY_FCLI_INSTALL_DIR:-$HOME/fortify/tools/bin}"
    echo "  Recommended version:     ${FORTIFY_RECOMMENDED_FCLI_VERSION:-<unset>}"
    echo
    echo "Add the fcli install directory to PATH or set FCLI_BIN before running fcli workflows."
    exit 0
fi

echo "  Binary:                  $fcli_cmd"
printf '  Version:                 '
"$fcli_cmd" --version 2>/dev/null || echo "<unable to read>"
echo "  Recommended version:     ${FORTIFY_RECOMMENDED_FCLI_VERSION:-<unset>}"
print_path_value "FCLI_USER_HOME" "${FCLI_USER_HOME:-}"
print_path_value "FORTIFY_DATA_DIR" "${FORTIFY_DATA_DIR:-}"
print_path_value "FCLI_DATA_DIR" "${FCLI_DATA_DIR:-}"
print_path_value "FCLI_STATE_DIR" "${FCLI_STATE_DIR:-}"
print_path_value "FCLI_CONFIG_DIR" "${FCLI_CONFIG_DIR:-}"
echo

echo "SSC sessions"
if "$fcli_cmd" ssc session list --help >/dev/null 2>&1; then
    if ! "$fcli_cmd" ssc session list -o table 2>/dev/null; then
        echo "  No SSC session list was returned. Log in to SSC or inspect fcli state permissions."
    fi
else
    echo "  This fcli build does not expose 'ssc session list' as expected for v3."
fi
echo

echo "Notes"
echo "  This runbook does not read fcli session files and does not print token environment variables."
echo "  For official fcli v3 documentation, see https://fortify.github.io/fcli/v3/."
