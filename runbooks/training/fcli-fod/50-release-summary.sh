#!/usr/bin/env bash
# fortifylab-runbook: true
# name: FoD release summary
# description: Generates a concise fcli FoD release summary for post-scan review.
# domain: Fortify on Demand
# category: FCLI FoD Training
# risk: low
# order: 75
# requires: bash
# params:
#   - name: release
#     description: FoD release id or <application>:<release> / <application>:<microservice>:<release>.
#     defaultFromEnv: FOD_RELEASE
#     required: false
#   - name: summary_file
#     description: Output file path or stdout.
#     default: stdout

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/fod-common.bash"

fod_require_fcli
RELEASE_VALUE="$(fod_require_release)"
SUMMARY_FILE="${SUMMARY_FILE:-stdout}"

fod_note "Summary" "Generating FoD release summary."
fcli fod action run release-summary --release "$RELEASE_VALUE" --file "$SUMMARY_FILE"
