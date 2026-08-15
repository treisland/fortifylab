#!/usr/bin/env bash
# fortifylab-runbook: true
# name: FoD fcli environment and session check
# description: Checks fcli availability, FoD-related environment variable presence, and local FoD session state without printing secrets.
# domain: Fortify on Demand
# category: FCLI FoD Training
# risk: low
# order: 70
# requires: bash
# params:
#   - name: login_if_needed
#     description: Set true only in a private shell to run fcli fod session login using configured fcli defaults.
#     default: false

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/fod-common.bash"

fod_require_fcli
fod_print_env_inventory
fod_show_fcli_version
fod_try_session_list
fod_login_if_requested

fod_note "Next" "Use 10-release-entitlement-guidance before submitting a scan to confirm the target release and entitlement state."
