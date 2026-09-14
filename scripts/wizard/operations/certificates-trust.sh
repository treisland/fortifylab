#!/usr/bin/env bash
# shellcheck shell=bash
# Module: operations/certificates-trust
# Responsibility: Export mkcert trust material and provide raw/guided environment editing entry points.
# Requires: FORTIFY_HOME_K8S; ENV_FILE; mkcert; error, note, title, ask, press_any,
#           wizard_log_event; env_prepare_backup, env_guided_section_editor,
#           domain_url_assistant, flight_plan_versions_menu, env_diagnostics,
#           env_repair_domain_urls, env_rollback_last, env_restore_selected.
# Exports: mkcert_caroot_path, mkcert_root_ca_source, mkcert_root_ca_export,
#          mkcert_trust_instructions, mkcert_root_ca_menu, raw_edit_env, edit_env.
# Side effects: Copies CA certificates and may edit ENV_FILE.
# Interactive: yes.

if [[ -n "${FORTIFYLAB_WIZARD_CERTIFICATES_TRUST_LOADED:-}" ]]; then
    return 0
fi
FORTIFYLAB_WIZARD_CERTIFICATES_TRUST_LOADED=1

mkcert_caroot_path() {
    mkcert -CAROOT 2>/dev/null
}

mkcert_root_ca_source() {
    local caroot
    caroot=$(mkcert_caroot_path) || return 1
    [ -n "$caroot" ] || return 1
    printf '%s/rootCA.pem\n' "$caroot"
}

mkcert_root_ca_export() {
    local src dest="$FORTIFY_HOME_K8S/certs/rootCA.pem"
    command -v mkcert >/dev/null 2>&1 || { error "mkcert is not installed."; return 1; }
    src=$(mkcert_root_ca_source) || { error "Could not locate mkcert CAROOT."; return 1; }
    [ -s "$src" ] || { error "mkcert rootCA.pem not found at $src. Run certificate generation first."; return 1; }
    mkdir -p "$(dirname "$dest")" || return 1
    cp "$src" "$dest" || return 1
    wizard_log_event "action=mkcert_root_ca_export destination=$dest"
    note "Copied public mkcert root CA to $dest"
    note "Only the public root CA certificate was copied; the private CA key was not touched."
}

mkcert_trust_instructions() {
    cat <<'EOF'

Trust the exported public root CA on client machines that open the lab URLs.
Never import, copy, or share the mkcert private CA key.

Windows:
  1. Open Manage user certificates.
  2. Import rootCA.pem into Trusted Root Certification Authorities.

macOS:
  1. Open Keychain Access.
  2. Import rootCA.pem into System or login keychain.
  3. Set the certificate to Always Trust for SSL.

Ubuntu/Debian:
  sudo cp rootCA.pem /usr/local/share/ca-certificates/fortifylab-mkcert.crt
  sudo update-ca-certificates

Firefox/NSS stores:
  Import rootCA.pem in Settings -> Privacy & Security -> Certificates,
  or use certutil for the relevant browser profile.
EOF
}

mkcert_root_ca_menu() {
    local src
    title "mkcert root CA"
    if command -v mkcert >/dev/null 2>&1; then
        src=$(mkcert_root_ca_source || true)
        printf '\n  mkcert CAROOT rootCA.pem: %s\n' "${src:-<unavailable>}"
        printf '  Export target:           %s\n' "$FORTIFY_HOME_K8S/certs/rootCA.pem"
    else
        printf '\n  mkcert is not installed. Install prerequisites first.\n'
    fi
    cat <<EOF

  1. Export public rootCA.pem to certs/rootCA.pem
  2. Show trust instructions

  r. Return
EOF
    echo
    ask choice "Select:"
    case "$choice" in
        1) mkcert_root_ca_export; mkcert_trust_instructions; press_any ;;
        2) mkcert_trust_instructions; press_any ;;
        [Rr]) return ;;
        *) error "Invalid"; sleep 1 ;;
    esac
}

raw_edit_env() {
    env_prepare_backup raw-editor || { error "Could not create .env backup."; return 1; }
    "${EDITOR:-nano}" "$ENV_FILE"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
}

edit_env() {
    local choice
    while true; do
        title "Configuration editor"
        cat <<EOF

  Lab Settings
    1. Kubernetes namespace
    2. Change lab domain and derived URLs

  Deployment Settings
    3. Deployment versions and Flight Plans
    4. Credentials, users, and passwords
    5. Advanced service URLs

  Validation and Repair
    6. Validate configuration
    7. Repair derived URLs from domain

  Certificates and Trust
    8. Export root CA and trust instructions

  Backups and Advanced
    9. Roll back last .env change
    10. Restore selected .env backup
    11. Open raw .env editor

  q. Quit safely
  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) env_guided_section_editor "Kubernetes namespace" identity || return $? ;;
            2) domain_url_assistant ;;
            3) flight_plan_versions_menu || return $? ;;
            4) env_guided_section_editor "Credentials, users, and passwords" credentials || return $? ;;
            5) env_guided_section_editor "Advanced service URLs" urls || return $? ;;
            6) env_diagnostics; press_any ;;
            7) env_repair_domain_urls; press_any ;;
            8) mkcert_root_ca_menu ;;
            9) env_rollback_last; press_any ;;
            10) env_restore_selected; press_any ;;
            11) raw_edit_env; press_any ;;
            [Qq]) clear; exit 0 ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


# ============================================================
# Prerequisites menu
# ============================================================

