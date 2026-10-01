# shellcheck shell=bash
# Module: operations/certificates
# Responsibility: Certificate and secret menu actions plus fcli trust refresh after regeneration.
# Requires: certificate generators, secret helpers, fcli helpers, UI helpers
# Exports: certs_secrets_menu, fcli_reimport_trust_after_regen
# Side effects: May regenerate certificates and Secrets and refresh fcli trust after confirmation.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_CERTIFICATES_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_CERTIFICATES_LOADED=1

# Certs + Secrets generation
# ============================================================

certs_secrets_menu() {
    title "Generate certs + secrets"
    cat <<EOF

  This rebuilds the lab's TLS chain and recreates every k8s Secret
  in the '$NAMESPACE' namespace.

  WARNING: rebuilding rotates SSC's secret.key, which invalidates any
  encrypted credentials already stored in the SSC database. Only run
  this on a fresh deploy or immediately before destroying SSC's data.

EOF
    echo "  1. Run scripts/create-certs.sh"
    echo "  2. Run scripts/create-secrets.sh"
    echo "  3. Run both (in order)"
    echo
    echo "  r. Return"
    echo
    ask choice "Select:"

    case "$choice" in
        1) ( bash "$FORTIFY_HOME_K8S/scripts/create-certs.sh" ) && fcli_reimport_trust_after_regen; press_any ;;
        2) ( bash "$FORTIFY_HOME_K8S/scripts/create-secrets.sh" );      press_any ;;
        3) ( bash "$FORTIFY_HOME_K8S/scripts/create-certs.sh" \
             && bash "$FORTIFY_HOME_K8S/scripts/create-secrets.sh" ) && fcli_reimport_trust_after_regen; press_any ;;
        [Rr]) return ;;
        *) error "Invalid"; sleep 1 ;;
    esac
}

# fcli_reimport_trust_after_regen — re-imports the freshly regenerated lab
# truststore into fcli's trust config every time, unconditionally (unlike
# fcli_activate, which skips when env-var state already looks active). Cert
# regeneration rewrites the truststore file's content in place, and we don't
# want to depend on fcli's "set" command re-reading that path live rather
# than snapshotting it — always re-run so it's correct either way. No-op if
# fcli isn't installed or DEFAULT_PASS isn't available.
fcli_reimport_trust_after_regen() {
    { [ -x "$FORTIFY_FCLI_INSTALL_DIR/fcli" ] || command -v fcli >/dev/null 2>&1; } || return 0
    [ -n "${DEFAULT_PASS:-}" ] || return 0
    fcli_configure_lab_trust "$(fcli_truststore_path)" || true
}


# ============================================================
