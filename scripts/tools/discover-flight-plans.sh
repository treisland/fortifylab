#!/usr/bin/env bash
# Draft candidate Flight Plan TOML from Docker Hub tags. This never edits the catalog.

set -euo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

exec python3 "$FORTIFY_HOME_K8S/scripts/tools/flight-plans.py" discover "$@"
