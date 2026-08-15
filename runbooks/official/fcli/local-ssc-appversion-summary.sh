#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC issue summary
# description: Generates a concise fcli SSC application-version issue summary for local lab review.
# domain: Local lab: SSC
# category: FCLI
# risk: low
# order: 80
# requires: bash
# params:
#   - name: appversion
#     description: SSC application version as <application>:<version>.
#     default: Fortify Lab Training:Synthetic
#     required: true
#   - name: summary_file
#     description: Output file path or stdout.
#     default: stdout
#     required: true
#   - name: filtersets
#     description: Optional comma-separated filter set names, guids, or default.
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
SUMMARY_FILE="${SUMMARY_FILE:-stdout}"

echo "Local SSC issue summary"
ssc_print_target "$APPVERSION_VALUE"
printf '  Summary output:          %s\n' "$SUMMARY_FILE"
if [[ -n "${FILTERSETS:-}" ]]; then
  printf '  Filter sets:             %s\n' "$FILTERSETS"
fi
echo

cmd=("$FCLI_CMD" ssc action run --ssc-session "$SESSION_VALUE" appversion-summary --appversion "$APPVERSION_VALUE" --file "$SUMMARY_FILE")
if [[ -n "${FILTERSETS:-}" ]]; then
  cmd+=(--filtersets "$FILTERSETS")
fi

ssc_note "Summary" "Generating SSC application-version summary."
"${cmd[@]}"
