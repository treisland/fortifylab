#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Local SSC upload FPR
# description: Validates a local FPR path and uploads it to a local SSC application version after explicit confirmation.
# domain: Local lab: SSC
# category: FCLI
# risk: high
# order: 60
# requires: bash
# params:
#   - name: appversion
#     description: SSC application version as <application>:<version>.
#     default: Fortify Lab Training:Synthetic
#     required: true
#   - name: fpr_file
#     description: Local .fpr file path to upload.
#     required: true
#   - name: session_name
#     description: fcli SSC session name.
#     default: fortifylab
#     required: true
#   - name: confirm_local_ssc_upload
#     description: Set yes to upload the local FPR to local SSC.
#     default: no
#     required: true

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/ssc-common.bash"

ssc_require_fcli
ssc_require_command_help "SSC artifact upload" ssc artifact upload

APPVERSION_VALUE="$(ssc_require_appversion)"
SESSION_VALUE="$(ssc_session_name)"
: "${FPR_FILE:?FPR_FILE is required. Provide a local .fpr file path.}"

if [[ ! -f "$FPR_FILE" ]]; then
  printf 'FPR_FILE does not exist or is not a regular file: %s\n' "$FPR_FILE" >&2
  exit 2
fi
if [[ ! -r "$FPR_FILE" ]]; then
  printf 'FPR_FILE is not readable: %s\n' "$FPR_FILE" >&2
  exit 2
fi
case "$FPR_FILE" in
  *.fpr|*.FPR) ;;
  *)
    printf 'FPR_FILE must point to a .fpr file: %s\n' "$FPR_FILE" >&2
    exit 2
    ;;
esac

echo "Local SSC FPR upload"
ssc_print_target "$APPVERSION_VALUE"
printf '  FPR file:                %s\n' "$FPR_FILE"
echo

if ! ssc_confirmed CONFIRM_LOCAL_SSC_UPLOAD; then
  cat <<UPLOAD
Upload skipped. This runbook changes local SSC state only when confirmed.

To upload this FPR intentionally, rerun with:
  CONFIRM_LOCAL_SSC_UPLOAD=yes

Command shape:
  fcli ssc artifact upload --ssc-session "$SESSION_VALUE" --appversion "$APPVERSION_VALUE" --file "$FPR_FILE"
UPLOAD
  exit 0
fi

ssc_note "Upload" "Uploading the local FPR to SSC. No token or session file contents are printed."
"$FCLI_CMD" ssc artifact upload \
  --ssc-session "$SESSION_VALUE" \
  --appversion "$APPVERSION_VALUE" \
  --file "$FPR_FILE"

ssc_note "Next" "Run local-ssc-policy-check.sh and local-ssc-appversion-summary.sh after SSC finishes processing the artifact."
