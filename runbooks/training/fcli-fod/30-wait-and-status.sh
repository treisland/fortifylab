#!/usr/bin/env bash
# fortifylab-runbook: true
# name: FoD wait and scan status
# description: Waits for a stored or supplied FoD SAST scan and then lists recent scan status for the release.
# domain: Fortify on Demand
# category: FCLI FoD Training
# risk: low
# order: 73
# requires: bash
# params:
#   - name: release
#     description: FoD release id or <application>:<release> / <application>:<microservice>:<release>.
#     defaultFromEnv: FOD_RELEASE
#     required: false
#   - name: scan_ref
#     description: fcli scan reference to wait for, usually ::scan:: from the upload runbook.
#     default: ::scan::
#   - name: wait_for_scan
#     description: Set true to wait for scan completion; false only lists status.
#     default: false

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/fod-common.bash"

fod_require_fcli
RELEASE_VALUE="$(fod_require_release)"
SCAN_REF="${SCAN_REF:-::scan::}"

if [[ "${WAIT_FOR_SCAN:-false}" == "true" ]]; then
  fod_note "Wait" "Waiting for FoD SAST scan. For fcli variables, release-id:scan-id is resolved by fcli."
  fcli fod sast-scan wait-for "$SCAN_REF"
else
  printf 'Skipping wait. Set WAIT_FOR_SCAN=true to wait for %s.\n' "$SCAN_REF"
fi

fod_note "Status" "Listing recent SAST scans for the release."
fcli fod sast-scan list --release "$RELEASE_VALUE"

fod_note "Next" "Use 40-policy-check and 50-release-summary after scan completion."
