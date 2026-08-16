#!/bin/bash

set -eo pipefail

if [ -z "$FORTIFY_HOME_K8S" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

source "$FORTIFY_HOME_K8S/.env"
# shellcheck source=../../../scripts/lib/dependency-health.sh
source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
# shellcheck source=../../../scripts/lib/coredns-lab-hosts.sh
source "$FORTIFY_HOME_K8S/scripts/lib/coredns-lab-hosts.sh"
RELEASE_OVERLAY_HELM_ARGS=()
if [ -f "$FORTIFY_HOME_K8S/scripts/lib/release-overlays.sh" ]; then
    # shellcheck source=../../../scripts/lib/release-overlays.sh
    source "$FORTIFY_HOME_K8S/scripts/lib/release-overlays.sh"
    release_overlay_load scdast/scanner
fi

fortify_ensure_coredns_lab_hosts

health_dast_core_ready

CURRENT_DIR="$( dirname "${BASH_SOURCE[0]}" )"

microk8s helm -n "$NAMESPACE" upgrade -i sdast-scanner oci://registry-1.docker.io/fortifydocker/helm-scancentral-dast-scanner --version "$FORTIFY_SCDAST_CHART_VERSION" --timeout 60m \
	--create-namespace \
	--set imagePullSecrets[0].name=regcred \
	--set dastApiServiceURL=$SCDAST_URL \
	--set serviceTokenSecretName=scdast-service-token \
	--set allowNonTrustedServerCertificate=true \
	-f $CURRENT_DIR/resource_override.yaml \
	"${RELEASE_OVERLAY_HELM_ARGS[@]}"

microk8s kubectl -n "$NAMESPACE" scale statefulset sdast-scanner-scancentral-dast-scanner --replicas=1
