# shellcheck shell=bash
# Module: operations/configuration-actions
# Responsibility: Configuration menu plus DNS, SSC token, LIM, and rules certificate actions.
# Requires: environment updater, certificate helpers, dashboard-access, UI helpers
# Exports: configure_menu, configure_dns, configure_ssc_token, configure_lim, refresh_rules_cert
# Side effects: Mutates DNS, Kubernetes Secrets, LIM configuration, or rules certificates after operator input.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_CONFIGURATION_ACTIONS_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_CONFIGURATION_ACTIONS_LOADED=1

# Configure: DNS, SSC token, LIM license, rulepack cert refresh
# ============================================================

configure_menu() {
    while true; do
        title "Configure"
        cat <<EOF

  1. DNS — print /etc/hosts entries + apply CoreDNS hosts override
  2. Apply SSC ControllerToken to ScanCentral SAST
  3. LIM — DAST license & default pool (manual instructions)
  4. Refresh update.fortify.com cert in truststore
  5. Kubernetes Dashboard access

  r. Return
EOF
        echo
        ask choice "Select:"

        case "$choice" in
            1) configure_dns;        press_any ;;
            2) configure_ssc_token;  press_any ;;
            3) configure_lim;        press_any ;;
            4) refresh_rules_cert;   press_any ;;
            5) dashboard_access_menu ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

configure_dns() {
    local ip expected_hosts
    ip=$(fortify_lab_node_ip)
    expected_hosts=$(fortify_lab_hostnames_inline)
    cat <<EOF

  -- Client side ------------------------------------------------
  Add to your client's /etc/hosts (or Pi-hole DNS):

    $ip   $expected_hosts

  Use the MicroK8s lab node IP shown above. If the names point at a Proxmox,
  Traefik, or other reverse-proxy endpoint without matching routes, browsers
  commonly show TRAEFIK DEFAULT CERT and then a plain 404 page.

  -- In-cluster side --------------------------------------------
  Pods inside the cluster need to resolve $DOMAIN themselves
  (e.g. ScanCentral SAST workers call https://sast.$DOMAIN/scancentral-ctrl).
  We patch CoreDNS's hosts plugin so they resolve to this node's IP.

EOF
    if confirm "Apply CoreDNS hosts override now?"; then
        fortify_ensure_coredns_lab_hosts || return 1
    fi
}

configure_ssc_token() {
    local token encoded_token
    cat <<EOF

  In SSC: Administration → ScanCentral SAST → Tokens →
          Create token of type 'ScanCentralCtrlToken'.
          Copy the value below.

EOF
    read -rsp "Paste ControllerToken (input hidden; empty cancels): " token
    echo
    [ -z "$token" ] && return
    if ! $HELM -n "$NAMESPACE" status scancentral-sast &>/dev/null; then
        error "ScanCentral SAST is not deployed yet."
        return
    fi
    encoded_token=$(printf '%s' "$token" | base64 | tr -d '\n')
    token=""
    if ! printf '{"metadata":{"annotations":{"fortify.dev/ssc-controller-token-configured":"true"}},"data":{"scancentral-ssc-scancentral-ctrl-secret":"%s"}}\n' \
        "$encoded_token" | $KUBECTL -n "$NAMESPACE" patch secret fortify-secrets \
        --type=merge --patch-file /dev/stdin >/dev/null; then
        encoded_token=""
        error "Could not update the protected ScanCentral SSC credential."
        return 1
    fi
    encoded_token=""
    if ! $HELM -n "$NAMESPACE" upgrade scancentral-sast \
        oci://registry-1.docker.io/fortifydocker/helm-scancentral-sast \
        --version "$FORTIFY_SCSAST_CHART_VERSION" --reuse-values \
        --set-string controller.sscScanCentralCtrlToken= \
        --set-string secrets.fortifyLicense= \
        --set-string secrets.workerAuthToken= \
        --set-string secrets.clientAuthToken= \
        --set-string secrets.sscScanCentralCtrlSecret= >/dev/null; then
        error "The Secret was updated, but legacy token metadata could not be cleared from the Helm release."
        return 1
    fi
    $KUBECTL -n "$NAMESPACE" rollout restart statefulset/scancentral-sast-controller >/dev/null
    if ! $KUBECTL -n "$NAMESPACE" rollout status statefulset/scancentral-sast-controller --timeout=300s; then
        error "The token was updated, but the SAST controller did not become ready."
        return 1
    fi
    note "ControllerToken updated without placing it in terminal output, process arguments, files, or Helm values."
}

configure_lim() {
    cat <<EOF

  LIM needs a DAST license file uploaded and a Default scanner pool
  configured before SCDAST can run scans. Both steps are done in
  LIM's web UI:

    1. Open ${LIM_URL:-https://lim.$DOMAIN}
    2. Sign in as lim_admin. Retrieve the lab-generated password from
       URLs & credentials if you need to recover it.
    3. Upload your DAST license file.
    4. Create a pool named 'Default' (matches \$LIM_POOL_NAME in .env).
    5. Generate seats / activate as documented by Fortify.

  After that, redeploy SCDAST (Apps → ScanCentral DAST → Start/Upgrade)
  so the scanner can authenticate to LIM.

EOF
}

refresh_rules_cert() {
    cat <<EOF

  Re-imports the current update.fortify.com leaf and root CA into the
  truststore. Run this when SSC reports a PKIX/handshake error fetching
  rulepacks (typically every 13 months when the leaf rotates).

EOF
    confirm "Refresh now?" || return

    local update_chain root_ca
    update_chain=$(mktemp)
    root_ca=$(mktemp)

    openssl s_client -servername "$FORTIFY_RULES_DOMAIN" \
        -connect "$FORTIFY_RULES_DOMAIN":443 -showcerts </dev/null 2>/dev/null \
      | awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > "$update_chain"

    awk -v last="$(grep -c '^-----BEGIN CERTIFICATE-----' "$update_chain")" '
        /-----BEGIN CERTIFICATE-----/{c++}
        c==last' "$update_chain" > "$root_ca"

    keytool -delete -alias update-fortify-root-ca -keystore "$TRUSTSTORE" \
        -storepass "$DEFAULT_PASS" 2>/dev/null || true
    keytool -import -alias update-fortify-root-ca -file "$root_ca" \
        -keystore "$TRUSTSTORE" -storepass "$DEFAULT_PASS" -noprompt

    rm -f "$update_chain" "$root_ca"

    # Push back into the live secret + restart SSC.
    $KUBECTL -n "$NAMESPACE" patch secret fortify-secrets \
        --type=merge -p "{"data":{"truststore":"$(base64 -w0 < "$TRUSTSTORE")"}}"
    $KUBECTL -n "$NAMESPACE" delete pod ssc-webapp-0 --ignore-not-found
    note "Truststore refreshed; SSC restarting."
}


# ============================================================
