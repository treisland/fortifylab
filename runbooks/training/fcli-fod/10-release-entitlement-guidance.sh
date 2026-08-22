#!/usr/bin/env bash
# fortifylab-runbook: true
# name: FoD release and entitlement guidance
# description: Shows safe fcli commands for validating a FoD release and entitlement before scan upload.
# domain: Fortify on Demand
# category: FCLI FoD Training
# risk: low
# order: 71
# requires: bash
# params:
#   - name: release
#     description: FoD release id or <application>:<release> / <application>:<microservice>:<release>.
#     defaultFromEnv: FOD_RELEASE
#     required: false
#   - name: run_lookup
#     description: Set true to run read-only release and entitlement lookup commands against FoD.
#     default: false

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/fod-common.bash"

fod_require_fcli
fod_print_env_inventory

RELEASE_VALUE="$(fod_require_release)"

fod_note "Release" "Target release was provided. Value is not treated as a secret, but keep customer names out of shared logs."
printf 'Release target: %s\n' "$RELEASE_VALUE"

cat <<GUIDANCE

Pre-upload checklist:
  1. Confirm this is the intended FoD tenant. FoD is external SaaS.
  2. Confirm the release exists and has SAST settings configured.
  3. Confirm the tenant has an available entitlement for the planned scan type.
  4. Confirm policy gates are understood before running post-scan checks.

Useful fcli v3 command shapes:
  fcli fod release get --release "$RELEASE_VALUE"
  fcli fod entitlement list
  fcli fod action run setup-release --release "$RELEASE_VALUE" --scan-types sast

Only run setup-release when you intentionally want fcli to create/configure FoD release state.
GUIDANCE

if [[ "${RUN_LOOKUP:-false}" == "true" ]]; then
  fod_note "Read-only lookup" "Running release and entitlement lookups."
  fcli fod release get --release "$RELEASE_VALUE"
  fcli fod entitlement list
else
  printf '\nSkipping live lookup. Set RUN_LOOKUP=true to query FoD.\n'
fi
