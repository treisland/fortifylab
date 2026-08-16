#!/usr/bin/env bash
# SSC 25.2 chart compatibility overlay.
#
# The 25.2 helm-ssc chart requires the older secretRef contract. The shared
# start script keeps the newer split secret/key values for current charts, and
# this overlay maps the selected 25.2 Flight Plan back to the single
# fortify-secrets Secret and its existing key names.

RELEASE_OVERLAY_HELM_ARGS+=(
  --set secretRef.name=fortify-secrets
  --set secretRef.keys.sscLicenseEntry=fortify.license
  --set secretRef.keys.sscAutoconfigEntry=ssc.autoconfig
  --set secretRef.keys.httpCertificateKeystoreFileEntry=keystore.jks
  --set secretRef.keys.httpCertificateKeyPasswordEntry=key_password
  --set secretRef.keys.httpCertificateKeystorePasswordEntry=keystore_password
  --set secretRef.keys.sscSecretKeyEntry=secret.key
  --set secretRef.keys.jvmTruststoreFileEntry=jvm_truststore
  --set secretRef.keys.jvmTruststorePasswordEntry=jvm_truststore_password
  --set secretRef.keys.httpTruststoreFileEntry=http_truststore
  --set secretRef.keys.httpTruststorePasswordEntry=http_truststore_password
)
