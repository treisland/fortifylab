#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Configure fcli lab TLS trust
# description: Checks Fortify Lab's generated JVM truststore and shows secret-safe fcli trust exports for local SSC workflows.
# domain: Local lab: SSC
# category: FCLI trust
# risk: low
# order: 20
# requires: bash
# params:
#   - name: truststore
#     description: Fortify Lab JKS truststore. Defaults to TRUSTSTORE, then FORTIFY_CERTS/truststore.
#     defaultFromEnv: TRUSTSTORE
#     required: false
#   - name: show_exports
#     description: Show copy/paste-safe export commands with the password placeholder redacted.
#     default: true
#     required: true

set -euo pipefail

resolve_truststore() {
    if [ -n "${TRUSTSTORE:-}" ]; then
        printf '%s
' "$TRUSTSTORE"
    elif [ -n "${FORTIFY_CERTS:-}" ]; then
        printf '%s/truststore
' "$FORTIFY_CERTS"
    else
        printf '%s/certs/truststore
' "${FORTIFY_HOME_K8S:-$PWD}"
    fi
}

truststore_path="$(resolve_truststore)"

if [ ! -s "$truststore_path" ]; then
    echo "Lab truststore was not found at: $truststore_path"
    echo "Run Generate TLS certificates first, then rerun this runbook or Tools and FCLI readiness -> Configure fcli trust for lab TLS."
    exit 1
fi

echo "fcli lab TLS trust"
echo "  Truststore:              $truststore_path"
echo "  Type:                    JKS"
echo "  Password source:         DEFAULT_PASS from the private FortifyLab environment"
echo

if [ "${FCLI_TRUSTSTORE:-}" = "$truststore_path" ] && [ "${FCLI_TRUSTSTORE_TYPE:-}" = "JKS" ] && [ -n "${FCLI_TRUSTSTORE_PWD:-}" ]; then
    echo "Current shell:             fcli trust environment is active"
else
    echo "Current shell:             fcli trust environment is not fully active"
fi

echo
cat <<EOF
Use the wizard option for the current shell:
  Tools and FCLI readiness -> Configure fcli trust for lab TLS

This avoids the common fcli PKIX error when Java does not trust the lab-local mkcert CA.
EOF

if [ "${SHOW_EXPORTS:-true}" = "true" ]; then
    cat <<EOF

Secret-safe command shape for a private shell:
  export FCLI_TRUSTSTORE="$truststore_path"
  export FCLI_TRUSTSTORE_TYPE="JKS"
  export FCLI_TRUSTSTORE_PWD='<DEFAULT_PASS from your private .env>'

Do not paste DEFAULT_PASS values into screenshots, shared terminals, runbook parameters, or committed files.
EOF
fi
