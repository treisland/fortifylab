#!/usr/bin/env bash
# fortifylab-runbook: true
# name: FoD policy check
# description: Runs the fcli FoD policy check action for a release and returns the action exit code.
# domain: Fortify on Demand
# category: FCLI FoD Training
# risk: low
# order: 74
# requires: bash
# params:
#   - name: release
#     description: FoD release id or <application>:<release> / <application>:<microservice>:<release>.
#     defaultFromEnv: FOD_RELEASE
#     required: false

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/fod-common.bash"

fod_require_fcli
RELEASE_VALUE="$(fod_require_release)"

fod_note "Policy" "Running FoD check-policy action. A failing FoD policy returns a non-zero exit code."
fcli fod action run check-policy --release "$RELEASE_VALUE"
