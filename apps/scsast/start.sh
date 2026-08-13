#!/bin/bash

set -eo pipefail

# Load the environment variables
if [ -z "$FORTIFY_HOME_K8S" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

source "$FORTIFY_HOME_K8S/.env"
# shellcheck source=../../scripts/lib/dependency-health.sh
source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
# shellcheck source=../../scripts/lib/k8s-hostnames.sh
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-hostnames.sh"
# shellcheck source=../../scripts/lib/traefik-backend.sh
source "$FORTIFY_HOME_K8S/scripts/lib/traefik-backend.sh"
# shellcheck source=../../scripts/lib/coredns-lab-hosts.sh
source "$FORTIFY_HOME_K8S/scripts/lib/coredns-lab-hosts.sh"

fortify_require_k8s_hostname SCSAST "$SCSAST"
fortify_ensure_coredns_lab_hosts

if [ "${FORTIFY_SCSAST_REQUIRE_SSC:-0}" = "1" ]; then
    health_ssc_ready
fi

SCSAST_WORKERS_ENABLED="${FORTIFY_SCSAST_WORKERS_ENABLED:-true}"
SCSAST_WORKER_REPLICAS="${FORTIFY_SCSAST_WORKER_REPLICAS:-1}"
case "$SCSAST_WORKERS_ENABLED" in
    true|false) ;;
    *) printf 'ERROR: FORTIFY_SCSAST_WORKERS_ENABLED must be true or false.\n' >&2; exit 1 ;;
esac
[[ "$SCSAST_WORKER_REPLICAS" =~ ^[0-9]+$ ]] || { printf 'ERROR: FORTIFY_SCSAST_WORKER_REPLICAS must be a non-negative integer.\n' >&2; exit 1; }

# Get the current directory where this script resides
CURRENT_DIR="$(dirname -- "${BASH_SOURCE[0]}")"

microk8s helm -n "$NAMESPACE" upgrade -i scancentral-sast oci://registry-1.docker.io/fortifydocker/helm-scancentral-sast --version "$FORTIFY_SCSAST_CHART_VERSION" \
--create-namespace \
--set imagePullSecrets[0].name=regcred \
--set-file trustedCertificates[0]=$ROOTCA_CERT \
--set-file trustedCertificates[1]=$SERVER_CERT \
--set secrets.secretName=fortify-secrets \
--set controller.image.tag="$FORTIFY_SCSAST_CTRL_IMAGE_TAG" \
--set controller.thisUrl="$SCSAST_CTRL_URL" \
--set controller.sscUrl="$SSC_URL" \
--set controller.persistence.enabled=true \
--set controller.persistence.accessMode=ReadWriteOnce \
--set controller.persistence.storageClass=nfs \
--set controller.enabled=true \
--set controller.truststoreSecret="" \
--set controller.serverCertificateKeystoreSecret=fortify-secrets \
--set controller.serverCertificateKeystoreKey=keystore.jks \
--set controller.serverCertificateKeystorePasswordSecret=fortify-secrets \
--set controller.serverCertificateKeystorePasswordKey=keystore_password \
--set controller.serverCertificateKeyPasswordSecret=fortify-secrets \
--set controller.serverCertificateKeyPasswordKey=key_password \
--set controller.serverCertificateKeyAliasSecret=fortify-secrets \
--set controller.serverCertificateKeyAliasKey=keystore_alias \
--set controller.ingress.enabled=true \
--set controller.ingress.className=public \
--set controller.ingress.hosts[0].host="$SCSAST" \
--set controller.ingress.hosts[0].paths[0].path=/ \
--set controller.ingress.hosts[0].paths[0].pathType=Prefix \
--set controller.ingress.tls[0].secretName=tls \
--set controller.ingress.tls[0].hosts[0]="$SCSAST" \
--set controller.ingress.annotations."nginx\.ingress\.kubernetes\.io/proxy-body-size"=1G \
--set controller.ingress.annotations."nginx\.ingress\.kubernetes\.io/backend-protocol"=HTTPS \
--set-string controller.ingress.annotations."traefik\.ingress\.kubernetes\.io/router\.tls"=true \
--set-string controller.ingress.annotations."traefik\.ingress\.kubernetes\.io/service\.serversscheme"=https \
--set workers.linux.enabled="$SCSAST_WORKERS_ENABLED" \
--set workers.linux.truststoreSecret="" \
--set workers.linux.controllerUrl="$SCSAST_CTRL_URL" \
--set workers.linux.persistence.enabled=false \
--set workers.linux.persistence.storageClass="nfs" \
--set workers.linux.persistence.size="20" \
--set workers.linux.image.tag="$FORTIFY_SCSAST_WORKER_IMAGE_TAG" \
-f $CURRENT_DIR/resource_override.yaml

fortify_annotate_traefik_https_service "$NAMESPACE" scancentral-sast-controller
microk8s kubectl -n "$NAMESPACE" scale statefulset scancentral-sast-controller --replicas=1
if microk8s kubectl -n "$NAMESPACE" get statefulset scancentral-sast-worker-linux >/dev/null 2>&1; then
    microk8s kubectl -n "$NAMESPACE" scale statefulset scancentral-sast-worker-linux --replicas="$SCSAST_WORKER_REPLICAS"
fi
