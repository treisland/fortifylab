#!/bin/bash

set -eo pipefail

if [ -z "$FORTIFY_HOME_K8S" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export FORTIFY_HOME_K8S
fi

source "$FORTIFY_HOME_K8S/.env"
# shellcheck source=../../scripts/lib/dependency-health.sh
source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"

# SSC database migrations must never start against an unavailable database.
health_mysql_ready

CURRENT_DIR="$( dirname "${BASH_SOURCE[0]}" )"

microk8s helm -n "$NAMESPACE" upgrade -i ssc \
		--create-namespace \
		oci://registry-1.docker.io/fortifydocker/helm-ssc \
		--version "$FORTIFY_SSC_CHART_VERSION" \
		--set urlHost="$SSC" \
		--set image.tag="$FORTIFY_SSC_IMAGE_TAG" \
		--set imagePullSecrets[0].name=regcred \
		--set sscLicenseSecret=fortify-secrets \
		--set sscLicenseKey=fortify.license \
		--set sscSecretKeySecret=fortify-secrets \
		--set sscSecretKeyKey=secret.key \
		--set sscAutoconfigSecret=fortify-secrets \
		--set sscAutoconfigKey=ssc.autoconfig \
		--set httpCertificateKeystoreSecret=fortify-secrets \
		--set httpCertificateKeystoreKey=keystore.jks \
		--set httpCertificateKeystorePasswordSecret=fortify-secrets \
		--set httpCertificateKeystorePasswordKey=keystore_password \
		--set httpCertificateKeyPasswordSecret=fortify-secrets \
		--set httpCertificateKeyPasswordKey=key_password \
		--set jvmTruststoreSecret=fortify-secrets \
		--set jvmTruststoreKey=jvm_truststore \
		--set jvmTruststorePasswordSecret=fortify-secrets \
		--set jvmTruststorePasswordKey=jvm_truststore_password \
		--set httpTruststoreSecret=fortify-secrets \
		--set httpTruststoreKey=http_truststore \
		--set httpTruststorePasswordSecret=fortify-secrets \
		--set httpTruststorePasswordKey=http_truststore_password \
		--set persistentVolumeClaim.size=20Gi \
		--set persistentVolumeClaim.storageClassName=nfs \
		--set resources.limits.memory=8Gi \
		--set resources.limits.cpu=1 \
		--set service.type=ClusterIP

microk8s kubectl -n "$NAMESPACE" apply -f $CURRENT_DIR/ingress.yaml

microk8s kubectl -n "$NAMESPACE" scale statefulsets ssc-webapp --replicas=1
