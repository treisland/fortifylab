#!/bin/bash
# Shared settings for the Jenkins integration scripts.

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

JENKINS_APP_DIR="$FORTIFY_HOME_K8S/apps/jenkins"
JENKINS_CHART_REPO_URL="https://charts.jenkins.io"

# Defaults keep older .env files working; .env.example documents each value.
jenkins_apply_defaults() {
    local domain="${DOMAIN:-fortifydemo.com}"
    export JENKINS="${JENKINS:-jenkins.$domain}"
    export JENKINS_URL="${JENKINS_URL:-https://$JENKINS}"
    export FORTIFY_JENKINS_CHART_VERSION="${FORTIFY_JENKINS_CHART_VERSION:-5.9.64}"
    export FORTIFY_JENKINS_IMAGE_TAG="${FORTIFY_JENKINS_IMAGE_TAG:-2.568.3-jdk21}"
    export FORTIFY_JENKINS_AGENT_IMAGE_TAG="${FORTIFY_JENKINS_AGENT_IMAGE_TAG:-3385.vf1123fb_515da_-1}"
    export FORTIFY_JENKINS_FCLI_INSTALL="${FORTIFY_JENKINS_FCLI_INSTALL:-auto}"
    export FORTIFY_JENKINS_FCLI_VERSION="${FORTIFY_JENKINS_FCLI_VERSION:-${FORTIFY_RECOMMENDED_FCLI_VERSION:-3.23.3}}"
    # Unset means the pinned default; set it to "" to skip Maven.
    export FORTIFY_JENKINS_MAVEN_VERSION="${FORTIFY_JENKINS_MAVEN_VERSION-3.9.16}"
    export JENKINS_AGENT_MAX="${JENKINS_AGENT_MAX:-2}"
    export JENKINS_ADMIN_USER="${JENKINS_ADMIN_USER:-admin}"
}

jenkins_load_env() {
    # shellcheck disable=SC1091
    source "$FORTIFY_HOME_K8S/.env"
    jenkins_apply_defaults
}

jenkins_validate_settings() {
    case "$FORTIFY_JENKINS_FCLI_INSTALL" in
        auto|manual) ;;
        *) printf 'ERROR: FORTIFY_JENKINS_FCLI_INSTALL must be auto or manual (got %s).\n' "$FORTIFY_JENKINS_FCLI_INSTALL" >&2; return 1 ;;
    esac
    [[ "$JENKINS_AGENT_MAX" =~ ^[1-9][0-9]*$ ]] || {
        printf 'ERROR: JENKINS_AGENT_MAX must be a positive integer (got %s).\n' "$JENKINS_AGENT_MAX" >&2
        return 1
    }
}

# Chart values with the .env settings filled in. Only the listed variables are
# substituted, so nothing else in the template is touched.
jenkins_render_values() {
    envsubst '${JENKINS} ${JENKINS_URL} ${FORTIFY_JENKINS_IMAGE_TAG} ${FORTIFY_JENKINS_AGENT_IMAGE_TAG} ${FORTIFY_JENKINS_FCLI_INSTALL} ${FORTIFY_JENKINS_FCLI_VERSION} ${FORTIFY_JENKINS_MAVEN_VERSION} ${JENKINS_AGENT_MAX}' \
        <"$JENKINS_APP_DIR/values.yaml.tpl"
}

# A StatefulSet rolling update waits for the current pod to become Ready
# before replacing it, so a jenkins-0 that crash-loops on the old spec blocks
# every upgrade (the Kubernetes "forced rollback" case). Replace the pod only
# when it is both on an old revision and not Ready; data stays on jenkins-home.
jenkins_replace_stuck_pod() {
    local kubectl="microk8s kubectl -n $NAMESPACE" waited=0 generation observed update pod_rev ready
    # Let the controller observe the new spec so updateRevision is current.
    while [ "$waited" -lt 30 ]; do
        generation=$($kubectl get statefulset jenkins -o jsonpath='{.metadata.generation}' 2>/dev/null) || return 0
        observed=$($kubectl get statefulset jenkins -o jsonpath='{.status.observedGeneration}' 2>/dev/null) || return 0
        [[ "$generation" =~ ^[0-9]+$ && "$observed" =~ ^[0-9]+$ ]] || break
        [ "$observed" -ge "$generation" ] && break
        sleep 2
        waited=$((waited + 2))
    done
    update=$($kubectl get statefulset jenkins -o jsonpath='{.status.updateRevision}' 2>/dev/null) || return 0
    pod_rev=$($kubectl get pod jenkins-0 -o jsonpath='{.metadata.labels.controller-revision-hash}' 2>/dev/null) || return 0
    [ -n "$update" ] && [ -n "$pod_rev" ] && [ "$pod_rev" != "$update" ] || return 0
    ready=$($kubectl get pod jenkins-0 -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null) || return 0
    [ "$ready" = True ] && return 0
    printf 'jenkins-0 is not ready and runs an old revision (%s, want %s); replacing it so the upgrade can roll out. Data on jenkins-home is kept.\n' "$pod_rev" "$update"
    $kubectl delete pod jenkins-0 --wait=false
}
