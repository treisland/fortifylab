#!/bin/bash
# Deploy or upgrade Jenkins (controller + Kubernetes agents) at
# https://$JENKINS using the lab TLS certificate. Agents trust the lab root CA
# and get fcli (see apps/jenkins/agent-init.sh).

set -eo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

# shellcheck source=common.sh
source "$FORTIFY_HOME_K8S/apps/jenkins/common.sh"
jenkins_load_env
# shellcheck source=../../scripts/lib/k8s-hostnames.sh
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-hostnames.sh"
# shellcheck source=../../scripts/lib/coredns-lab-hosts.sh
source "$FORTIFY_HOME_K8S/scripts/lib/coredns-lab-hosts.sh"
# shellcheck source=../../scripts/lib/tls.sh
source "$FORTIFY_HOME_K8S/scripts/lib/tls.sh"

jenkins_validate_settings
fortify_require_k8s_hostname JENKINS "$JENKINS"

# mkcert certificates are wildcards for *.$DOMAIN; a bring-your-own
# certificate must list the Jenkins host explicitly.
if ! fortify_tls_cert_covers_host "$SERVER_CERT" "$JENKINS"; then
    printf 'ERROR: The lab TLS certificate (%s) does not cover %s.\n' "$SERVER_CERT" "$JENKINS" >&2
    printf 'Add %s (or *.%s) to the certificate SANs, re-run the TLS certificates step, then retry.\n' "$JENKINS" "$DOMAIN" >&2
    exit 1
fi
if [ ! -s "$ROOTCA_CERT" ]; then
    printf 'ERROR: Lab root CA not found at ROOTCA_CERT=%s. Run the TLS certificates step first.\n' "$ROOTCA_CERT" >&2
    exit 1
fi
if ! microk8s kubectl -n "$NAMESPACE" get secret tls >/dev/null 2>&1; then
    printf 'ERROR: Kubernetes Secret "tls" is missing in namespace %s. Run the Kubernetes Secrets step first.\n' "$NAMESPACE" >&2
    exit 1
fi

fortify_ensure_coredns_lab_hosts

apply_generated() {
    microk8s kubectl -n "$NAMESPACE" apply -f -
}

microk8s kubectl -n "$NAMESPACE" create secret generic jenkins-admin \
    --from-literal=jenkins-admin-user="$JENKINS_ADMIN_USER" \
    --from-literal=jenkins-admin-password="${JENKINS_ADMIN_PASSWORD:-$DEFAULT_PASS}" \
    --dry-run=client -o yaml | apply_generated
# Re-running Start after rotating the lab CA updates what new pods trust.
microk8s kubectl -n "$NAMESPACE" create configmap fortifylab-root-ca \
    --from-file=rootCA.pem="$ROOTCA_CERT" \
    --dry-run=client -o yaml | apply_generated
microk8s kubectl -n "$NAMESPACE" create configmap jenkins-agent-init \
    --from-file=agent-init.sh="$JENKINS_APP_DIR/agent-init.sh" \
    --dry-run=client -o yaml | apply_generated
envsubst '${NAMESPACE}' <"$JENKINS_APP_DIR/pvc.yaml" | apply_generated

microk8s helm repo add jenkins "$JENKINS_CHART_REPO_URL" --force-update >/dev/null
microk8s helm repo update jenkins >/dev/null

VALUES_FILE="$(mktemp)"
trap 'rm -f "$VALUES_FILE"' EXIT
jenkins_render_values >"$VALUES_FILE"

microk8s helm -n "$NAMESPACE" upgrade -i jenkins jenkins/jenkins \
    --version "$FORTIFY_JENKINS_CHART_VERSION" \
    -f "$VALUES_FILE"

# Start after Stop: bring the controller back to one replica.
microk8s kubectl -n "$NAMESPACE" scale statefulset jenkins --replicas=1
jenkins_replace_stuck_pod
