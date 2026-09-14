# shellcheck shell=bash
# Module: operations/credentials
# Responsibility: Secret-safe credential retrieval, URL summaries, and login/trust guidance.
# Layer: operation/menu (legacy-compatible extraction)
# Requires: UI helpers, cluster_reachable, secret_key_exists, dashboard_access_menu, KUBECTL, NAMESPACE, URL/certificate globals.
# Exports: credential_*, certificate_trust_handoff, ssc_login_guidance, urls_creds*.
# Side effects: Reads Kubernetes Secrets; reveals a credential only after explicit confirmation.
# Interactive: yes.
[ -n "${FORTIFY_WIZARD_CREDENTIALS_LOADED:-}" ] && return 0
FORTIFY_WIZARD_CREDENTIALS_LOADED=1

credential_value_from_secret() {
    local secret="$1" key="$2" encoded
    cluster_reachable || { error "Cluster is not reachable."; return 1; }
    encoded=$($KUBECTL -n "$NAMESPACE" get secret "$secret" \
        -o "go-template={{ index .data \"$key\" }}" 2>/dev/null) || {
        error "Could not read secret $secret/$key."
        return 1
    }
    [ -n "$encoded" ] || { error "Secret value $secret/$key is empty or missing."; return 1; }
    printf '%s' "$encoded" | base64 -d
}

credential_present_label() {
    local secret="$1" key="$2"
    if cluster_reachable && secret_key_exists "$secret" "$key"; then
        printf '%savailable%s' "$GREEN" "$RESET"
    else
        printf '%sunavailable%s' "$YELLOW" "$RESET"
    fi
}

credential_reveal_once() {
    local label="$1" secret="$2" key="$3" confirmation
    title "Reveal credential once"
    cat <<EOF

  Credential: $label
  Source:     $secret/$key

  This may expose a password or token in your terminal scrollback or screen
  capture. The wizard will not write this value to logs, diagnostics, .env,
  or any file.

EOF
    ask confirmation "Type REVEAL to display this value once:"
    [ "$confirmation" = REVEAL ] || { note "Reveal cancelled."; press_any; return 1; }
    echo
    section "$label"
    credential_value_from_secret "$secret" "$key" || { press_any; return 1; }
    echo
    note "Press Enter to clear this screen and return to the credentials menu."
    read -r _
    clear
}

credential_reveal_menu() {
    local choice
    while true; do
        title "Reveal one credential"
        cat <<EOF

  1. LIM admin password
  2. LIM pool password
  3. ScanCentral SAST client auth token
  4. ScanCentral SAST worker auth token
  5. ScanCentral SAST SSC ControllerToken
  6. ScanCentral DAST service token
  7. ScanCentral DAST SSC service account password
  8. ScanCentral DAST database owner password
  9. ScanCentral DAST database standard user password

  b. Back
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) credential_reveal_once "LIM admin password" lim-admin-credentials password ;;
            2) credential_reveal_once "LIM pool password" lim-pool password ;;
            3) credential_reveal_once "ScanCentral SAST client auth token" fortify-secrets scancentral-client-auth-token ;;
            4) credential_reveal_once "ScanCentral SAST worker auth token" fortify-secrets scancentral-worker-auth-token ;;
            5) credential_reveal_once "ScanCentral SAST SSC ControllerToken" fortify-secrets scancentral-ssc-scancentral-ctrl-secret ;;
            6) credential_reveal_once "ScanCentral DAST service token" scdast-service-token service-token ;;
            7) credential_reveal_once "ScanCentral DAST SSC service account password" scdast-ssc-serviceaccount password ;;
            8) credential_reveal_once "ScanCentral DAST database owner password" scdast-db-owner password ;;
            9) credential_reveal_once "ScanCentral DAST database standard user password" scdast-db-standard password ;;
            [Bb]) return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

credential_retrieval_commands() {
    title "Credential retrieval commands"
    cat <<EOF

  Use these commands when you prefer to retrieve a value yourself. Values are
  decoded from Kubernetes Secrets and are not written by the wizard.

  LIM admin password:
    $KUBECTL -n $NAMESPACE get secret lim-admin-credentials -o go-template='{{ index .data "password" }}' | base64 -d

  LIM pool password:
    $KUBECTL -n $NAMESPACE get secret lim-pool -o go-template='{{ index .data "password" }}' | base64 -d

  SAST client auth token:
    $KUBECTL -n $NAMESPACE get secret fortify-secrets -o go-template='{{ index .data "scancentral-client-auth-token" }}' | base64 -d

  SAST worker auth token:
    $KUBECTL -n $NAMESPACE get secret fortify-secrets -o go-template='{{ index .data "scancentral-worker-auth-token" }}' | base64 -d

  SAST SSC ControllerToken:
    $KUBECTL -n $NAMESPACE get secret fortify-secrets -o go-template='{{ index .data "scancentral-ssc-scancentral-ctrl-secret" }}' | base64 -d

  DAST service token:
    $KUBECTL -n $NAMESPACE get secret scdast-service-token -o go-template='{{ index .data "service-token" }}' | base64 -d

  DAST SSC service account password:
    $KUBECTL -n $NAMESPACE get secret scdast-ssc-serviceaccount -o go-template='{{ index .data "password" }}' | base64 -d

EOF
    press_any
}

certificate_trust_handoff() {
    title "Certificate trust"
    cat <<EOF

  mkcert root CA:
    ${ROOTCA_CERT:-$FORTIFY_CERTS/rootCA.pem}

  Import the mkcert root CA into each client machine or browser trust store
  that will access the lab URLs. FortifyLab serves workload TLS from the
  Kubernetes Secret $NAMESPACE/tls and configures MicroK8s ingress to use it
  as the default certificate when the installed ingress addon supports that.

  Lab hostnames:
    ssc.$DOMAIN
    lim.$DOMAIN
    sast.$DOMAIN
    dast.$DOMAIN
    dashboard.$DOMAIN

EOF
    press_any
}

ssc_login_guidance() {
    title "SSC login guidance"
    cat <<EOF

  SSC URL:
    ${SSC_URL:-<unset>}

  Username:
    admin

  Password:
    Refer to the SSC documentation for the default administrator password.
    FortifyLab does not store or display that vendor default password.

  After first login, change the password inside SSC and store it in your own
  password manager.

EOF
    press_any
}

urls_creds_summary() {
    title "URLs & credentials"
    cat <<EOF

  Service URLs
    SSC             ${SSC_URL:-<unset>}
    LIM             ${LIM_URL:-<unset>}
    SAST controller ${SCSAST_CTRL_URL:-<unset>}
    DAST            ${SCDAST_URL:-<unset>}
    Dashboard       https://dashboard.$DOMAIN

  Login guidance
    SSC             admin / refer to the SSC documentation for the default password
    LIM             lim_admin / stored in lim-admin-credentials
    DAST            SSC user mapped to a DAST role
    Dashboard       generate a token from Kubernetes Dashboard access

  Credential availability
    LIM admin password              $(credential_present_label lim-admin-credentials password)
    LIM pool password               $(credential_present_label lim-pool password)
    SAST client auth token           $(credential_present_label fortify-secrets scancentral-client-auth-token)
    SAST worker auth token           $(credential_present_label fortify-secrets scancentral-worker-auth-token)
    SAST SSC ControllerToken         $(credential_present_label fortify-secrets scancentral-ssc-scancentral-ctrl-secret)
    DAST service token               $(credential_present_label scdast-service-token service-token)
    DAST SSC service account         $(credential_present_label scdast-ssc-serviceaccount password)

EOF
}

urls_creds() {
    local choice
    while true; do
        urls_creds_summary
        cat <<EOF
  1. Reveal one credential
  2. Show retrieval commands
  3. SSC login guidance
  4. Kubernetes Dashboard token menu
  5. Certificate trust instructions

  r. Return
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) credential_reveal_menu ;;
            2) credential_retrieval_commands ;;
            3) ssc_login_guidance ;;
            4) dashboard_access_menu ;;
            5) certificate_trust_handoff ;;
            [Rr]|"") return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

