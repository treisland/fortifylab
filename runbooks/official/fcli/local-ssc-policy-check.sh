#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC policy check
# description: Runs the fcli SSC check-policy action for a local SSC application version and returns the action exit code.
# domain: Local lab: SSC
# category: FCLI
# risk: low
# order: 70
# requires: bash
# params:
#   - name: appversion
#     description: SSC application version as <application>:<version>.
#     default: Fortify Lab Training:Synthetic
#     required: true
#   - name: filterset
#     description: Optional SSC filter set name or guid.
#     default: ""
#     required: false
#   - name: session_name
#     description: fcli SSC session name.
#     default: fortifylab
#     required: true

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/ssc-common.bash"

ssc_require_fcli
ssc_require_command_help "SSC action execution" ssc action run

APPVERSION_VALUE="$(ssc_require_appversion)"
SESSION_VALUE="$(ssc_session_name)"

echo "Local SSC policy check"
ssc_print_target "$APPVERSION_VALUE"
if [[ -n "${FILTERSET:-}" ]]; then
  printf '  Filter set:              %s\n' "$FILTERSET"
fi
echo

cmd=("$FCLI_CMD" ssc action run --ssc-session "$SESSION_VALUE" check-policy --appversion "$APPVERSION_VALUE")
if [[ -n "${FILTERSET:-}" ]]; then
  cmd+=(--filterset "$FILTERSET")
fi

ssc_note "Policy" "Running SSC check-policy. A failing policy returns a non-zero exit code."
"${cmd[@]}"
