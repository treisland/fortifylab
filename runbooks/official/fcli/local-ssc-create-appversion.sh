#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC create app version
# description: Creates or reuses a local SSC application version after explicit confirmation.
# domain: Local lab: SSC
# category: FCLI
# risk: medium
# order: 50
# requires: bash
# params:
#   - name: appversion
#     description: SSC application version as <application>:<version>.
#     default: Fortify Lab Training:Synthetic
#     required: true
#   - name: session_name
#     description: fcli SSC session name.
#     default: fortifylab
#     required: true
#   - name: confirm_local_ssc_create
#     description: Set yes to create or reuse the app version in local SSC.
#     default: no
#     required: true

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/ssc-common.bash"

ssc_require_fcli
ssc_require_command_help "SSC application-version creation" ssc appversion create

APPVERSION_VALUE="$(ssc_require_appversion)"
SESSION_VALUE="$(ssc_session_name)"

echo "Local SSC app-version creation"
ssc_print_target "$APPVERSION_VALUE"
echo

if ! ssc_confirmed CONFIRM_LOCAL_SSC_CREATE; then
  cat <<CREATE
Creation skipped. This runbook changes local SSC state only when confirmed.

To create or reuse this application version intentionally, rerun with:
  CONFIRM_LOCAL_SSC_CREATE=yes

Command shape:
  fcli ssc appversion create --ssc-session "$SESSION_VALUE" --skip-if-exists --auto-required-attrs "$APPVERSION_VALUE"
CREATE
  exit 0
fi

ssc_note "Create" "Creating or reusing the local SSC application version."
"$FCLI_CMD" ssc appversion create \
  --ssc-session "$SESSION_VALUE" \
  --skip-if-exists \
  --auto-required-attrs \
  "$APPVERSION_VALUE"

ssc_note "Next" "Upload a local FPR with local-ssc-upload-fpr.sh, then run policy and summary checks."
