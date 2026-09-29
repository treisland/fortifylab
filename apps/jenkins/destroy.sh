#!/bin/bash
# Remove Jenkins. Jobs, build history, and agent tools are kept on their
# volumes unless JENKINS_DESTROY_DATA=1 (the wizard asks separately).

set -eo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

CURRENT_DIR="$(dirname -- "${BASH_SOURCE[0]}")"

# shellcheck disable=SC1091
source "$FORTIFY_HOME_K8S/.env"
# shellcheck source=../../scripts/lib/k8s-destroy.sh
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-destroy.sh"

fortify_helm_delete_if_exists "$NAMESPACE" jenkins

microk8s kubectl -n "$NAMESPACE" delete secret jenkins-admin --ignore-not-found
microk8s kubectl -n "$NAMESPACE" delete configmap fortifylab-root-ca jenkins-agent-init --ignore-not-found

if [ "${JENKINS_DESTROY_DATA:-0}" = 1 ]; then
    envsubst '${NAMESPACE}' <"$CURRENT_DIR/pvc.yaml" | microk8s kubectl -n "$NAMESPACE" delete -f - --ignore-not-found
    printf 'Deleted Jenkins data volumes (jenkins-home, jenkins-agent-tools).\n'
else
    printf 'Kept Jenkins data volumes (jenkins-home, jenkins-agent-tools); Start restores jobs and history.\n'
fi
