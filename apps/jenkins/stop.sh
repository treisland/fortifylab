#!/bin/bash
# Stop the Jenkins controller; data and agent tools stay on their volumes.

set -eo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

# shellcheck disable=SC1091
source "$FORTIFY_HOME_K8S/.env"
# shellcheck source=../../scripts/lib/k8s-scale.sh
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-scale.sh"

fortify_scale_statefulset_if_exists "$NAMESPACE" jenkins 0
