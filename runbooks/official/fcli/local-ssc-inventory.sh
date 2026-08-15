#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC bounded inventory
# description: Lists bounded local SSC application and application-version inventory through an existing fcli SSC session.
# domain: Local lab: SSC
# category: FCLI
# risk: low
# order: 40
# requires: bash
# params:
#   - name: session_name
#     description: fcli SSC session name to use for inventory.
#     default: fortifylab
#     required: true
#   - name: max_records
#     description: Maximum records to fetch for each inventory section.
#     default: 25
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

run_inventory_section() {
    local title="$1"
    shift
    echo "$title"
    if "$fcli_cmd" "$@" --help >/dev/null 2>&1; then
        if ! "$fcli_cmd" "$@" --ssc-session "$SESSION_NAME" --fetch "$MAX_RECORDS" -o table 2>/dev/null; then
            echo "  Unable to read $title. Check session permissions and SSC readiness."
        fi
    else
        echo "  This fcli build does not expose '$*' as expected for v3."
    fi
    echo
}

: "${SESSION_NAME:?SESSION_NAME is required.}"

if ! is_positive_integer "${MAX_RECORDS:-}"; then
    echo "MAX_RECORDS must be a positive integer."
    exit 1
fi

fcli_cmd="$(resolve_fcli_bin || true)"
[ -n "$fcli_cmd" ] || {
    echo "fcli not found. Install it from the wizard's Tools and FCLI readiness screen or set FCLI_BIN."
    exit 1
}

echo "Local SSC bounded inventory"
echo "  SSC session:             $SESSION_NAME"
echo "  Max records per section: $MAX_RECORDS"
echo "  fcli binary:             $fcli_cmd"
echo

run_inventory_section "SSC applications" ssc app list
run_inventory_section "SSC application versions" ssc appversion list

echo "Inventory complete. No token values, session file contents, or fcli state files were printed."
