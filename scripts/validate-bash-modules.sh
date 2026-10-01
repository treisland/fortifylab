#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mapfile -d '' bash_files < <(
    find scripts/wizard/operations scripts/wizard/flight-plans \
        -type f -name '*.sh' -print0
)
bash_files+=(start_wizard.sh scripts/wizard/operations.sh)

bash -n "${bash_files[@]}"

if ! command -v shellcheck >/dev/null 2>&1; then
    printf '%s\n' "ERROR: shellcheck is required for Bash module validation." >&2
    exit 1
fi
shellcheck --severity=error -x "${bash_files[@]}"

python3 -m unittest \
    tests.test_operations_modularity \
    tests.test_phase3_architecture \
    tests.test_guided_wizard \
    tests.test_wizard_contract \
    tests.test_flight_plans
