# shellcheck shell=bash
# Module: operations/fcli
# Responsibility: fcli discovery, installation, PATH persistence, TLS trust configuration, status, and guidance.
# Layer: operation/menu (legacy-compatible extraction)
# Requires: UI helpers and FORTIFY_FCLI_*, FORTIFY_HOME_K8S, FORTIFY_CERTS/TRUSTSTORE, DEFAULT_PASS globals.
# Exports: fcli_* functions.
# Side effects: May download/install fcli and append non-secret PATH/trust hints to the selected shell profile.
# Interactive: fcli_tools_menu only.
[ -n "${FORTIFY_WIZARD_FCLI_LOADED:-}" ] && return 0
FORTIFY_WIZARD_FCLI_LOADED=1

fcli_path_entry_present() {
    local target="$1"
    case ":$PATH:" in
        *":$target:"*) return 0 ;;
        *) return 1 ;;
    esac
}

fcli_export_current_path() {
    local target="${1:-$FORTIFY_FCLI_INSTALL_DIR}"
    [ -d "$target" ] || return 1
    if fcli_path_entry_present "$target"; then
        return 0
    fi
    export PATH="$target:$PATH"
}

fcli_shell_profile_path() {
    if [ -n "${FORTIFY_FCLI_PROFILE_FILE:-}" ]; then
        printf '%s\n' "$FORTIFY_FCLI_PROFILE_FILE"
    elif [ -f "$HOME/.bashrc" ] || [ "${SHELL##*/}" = bash ]; then
        printf '%s/.bashrc\n' "$HOME"
    else
        printf '%s/.profile\n' "$HOME"
    fi
}

fcli_profile_has_path() {
    local profile="$1" target="${2:-$FORTIFY_FCLI_INSTALL_DIR}"
    [ -f "$profile" ] || return 1
    grep -F "$target" "$profile" >/dev/null 2>&1
}

fcli_persist_path() {
    local target="${1:-$FORTIFY_FCLI_INSTALL_DIR}" profile
    profile="$(fcli_shell_profile_path)"
    mkdir -p "$(dirname "$profile")" || return 1
    if fcli_profile_has_path "$profile" "$target"; then
        return 0
    fi
    {
        printf '\n# FortifyLab tools\n'
        printf 'export PATH="%s:$PATH"\n' "$target"
    } >> "$profile"
}


# fcli's own client truststore -- a superset of the JDK default CA bundle
# plus the lab/update.fortify.com anchors, not TRUSTSTORE (SSC's narrow,
# server-side-only JVM trust store). Falls back to TRUSTSTORE only when
# fcli-truststore hasn't been generated yet (existing lab, certs not
# regenerated since this split), so fcli still gets lab trust in the
# meantime -- regenerate certs to widen it to the public internet too.
fcli_truststore_path() {
    local certs truststore legacy
    certs="${FORTIFY_CERTS:-$FORTIFY_HOME_K8S/certs}"
    truststore="${FCLI_CLIENT_TRUSTSTORE:-}"
    legacy="${TRUSTSTORE:-$certs/truststore}"
    if [ -z "$truststore" ]; then
        truststore="$certs/fcli-truststore"
    fi
    if [ ! -s "$truststore" ] && [ -s "$legacy" ]; then
        printf '%s\n' "$legacy"
        return
    fi
    printf '%s\n' "$truststore"
}

fcli_trust_configured_current() {
    local truststore="${1:-$(fcli_truststore_path)}"
    [ "${FCLI_TRUSTSTORE:-}" = "$truststore" ] &&
        [ "${FCLI_TRUSTSTORE_TYPE:-}" = "JKS" ] &&
        [ -n "${FCLI_TRUSTSTORE_PWD:-}" ]
}

fcli_export_lab_trust() {
    local truststore="${1:-$(fcli_truststore_path)}"
    [ -s "$truststore" ] || return 1
    [ -n "${DEFAULT_PASS:-}" ] || return 2
    export FCLI_TRUSTSTORE="$truststore"
    export FCLI_TRUSTSTORE_TYPE="JKS"
    export FCLI_TRUSTSTORE_PWD="$DEFAULT_PASS"
}

fcli_profile_has_lab_trust_hints() {
    local profile="$1" truststore="${2:-$(fcli_truststore_path)}"
    [ -f "$profile" ] || return 1
    grep -F "export FCLI_TRUSTSTORE=\"$truststore\"" "$profile" >/dev/null 2>&1 &&
        grep -F 'export FCLI_TRUSTSTORE_TYPE="JKS"' "$profile" >/dev/null 2>&1
}

fcli_persist_lab_trust_hints() {
    local truststore="${1:-$(fcli_truststore_path)}" profile
    [ -s "$truststore" ] || return 1
    profile="$(fcli_shell_profile_path)"
    mkdir -p "$(dirname "$profile")" || return 1
    if fcli_profile_has_lab_trust_hints "$profile" "$truststore"; then
        return 0
    fi
    {
        printf '\n# FortifyLab fcli TLS trust hints; set the truststore password privately per shell.\n'
        printf 'export FCLI_TRUSTSTORE="%s"\n' "$truststore"
        printf 'export FCLI_TRUSTSTORE_TYPE="JKS"\n'
    } >> "$profile"
}

fcli_configure_persistent_trust() {
    local truststore="${1:-$(fcli_truststore_path)}" fcli_bin
    fcli_bin="$(fcli_path 2>/dev/null)" || return 1
    "$fcli_bin" config truststore set --file "$truststore" --type jks --password "$DEFAULT_PASS" >/dev/null 2>&1
}

fcli_configure_lab_trust() {
    local truststore="${1:-$(fcli_truststore_path)}" profile
    if [ ! -s "$truststore" ]; then
        error "Lab truststore not found at $truststore. Generate TLS certificates first."
        return 1
    fi
    if [ -z "${DEFAULT_PASS:-}" ]; then
        error "DEFAULT_PASS is required to activate fcli lab TLS trust for this shell."
        return 1
    fi
    fcli_export_lab_trust "$truststore" || return 1
    fcli_persist_lab_trust_hints "$truststore" || return 1
    profile="$(fcli_shell_profile_path)"
    note "Activated fcli lab TLS trust for this shell."
    note "Persisted non-secret truststore hints in $profile."
    if fcli_configure_persistent_trust "$truststore"; then
        note "Configured fcli's own persistent trust store (active for every future shell, no export needed)."
    else
        note "For future shells, export FCLI_TRUSTSTORE_PWD from DEFAULT_PASS in a private shell."
    fi
}

fcli_trust_status_line() {
    local truststore
    truststore="$(fcli_truststore_path)"
    if [ ! -s "$truststore" ]; then
        printf '%s Lab truststore missing at %s\n' "$WARN_MARK" "$truststore"
    elif fcli_trust_configured_current "$truststore"; then
        printf '%s FCLI lab TLS trust active for %s\n' "$OK_MARK" "$truststore"
    else
        printf '%s Lab truststore exists but fcli trust env is not active\n' "$WARN_MARK"
    fi
}

fcli_path() {
    command -v fcli 2>/dev/null && return 0
    if [ -x "$FORTIFY_FCLI_INSTALL_DIR/fcli" ]; then
        printf '%s\n' "$FORTIFY_FCLI_INSTALL_DIR/fcli"
        return 0
    fi
    return 1
}

# fcli_activate — transparently re-activates fcli's PATH and lab TLS trust
# whenever they're already installed/generated but not yet active in this
# process, the same "detect and fix, no manual step" treatment as
# ensure_active_groups gives microk8s/docker. Safe to call unconditionally
# (wizard startup, after cert regeneration): no-ops if fcli isn't installed
# or the truststore doesn't exist yet.
fcli_activate() {
    [ -x "$FORTIFY_FCLI_INSTALL_DIR/fcli" ] || command -v fcli >/dev/null 2>&1 || return 0
    fcli_export_current_path "$FORTIFY_FCLI_INSTALL_DIR" 2>/dev/null || true
    fcli_persist_path "$FORTIFY_FCLI_INSTALL_DIR" 2>/dev/null || true

    local truststore
    truststore="$(fcli_truststore_path)"
    [ -s "$truststore" ] || return 0
    [ -n "${DEFAULT_PASS:-}" ] || return 0
    fcli_trust_configured_current "$truststore" && return 0
    fcli_configure_lab_trust "$truststore" || true
}

fcli_installed_version() {
    local path
    path="$(fcli_path)" || return 1
    "$path" --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1
}

fcli_status_line() {
    local path version
    path=$(fcli_path || true)
    if [ -z "$path" ]; then
        printf '%s FCLI missing; recommended %s\n' "$WARN_MARK" "$FORTIFY_RECOMMENDED_FCLI_VERSION"
        return 0
    fi
    version=$(fcli_installed_version || true)
    if [ "$version" = "$FORTIFY_RECOMMENDED_FCLI_VERSION" ]; then
        printf '%s FCLI %s at %s\n' "$OK_MARK" "$version" "$path"
    elif [ -n "$version" ]; then
        printf '%s FCLI %s at %s; recommended %s\n' "$WARN_MARK" "$version" "$path" "$FORTIFY_RECOMMENDED_FCLI_VERSION"
    else
        printf '%s FCLI found at %s; version unknown; recommended %s\n' "$WARN_MARK" "$path" "$FORTIFY_RECOMMENDED_FCLI_VERSION"
    fi
}

fcli_print_status() {
    section "FCLI status"
    printf '  Recommended version: %s\n' "$FORTIFY_RECOMMENDED_FCLI_VERSION"
    printf '  Install directory:    %s\n' "$FORTIFY_FCLI_INSTALL_DIR"
    printf '  %s\n' "$(fcli_status_line)"
    printf '  %s\n' "$(fcli_trust_status_line)"
    cat <<EOF

  FCLI is needed only for local Fortify command-line workflows after the lab is
  running. Missing or mismatched FCLI does not block infrastructure deployment.
EOF
}

fcli_install_or_update() {
    local version="${FORTIFY_RECOMMENDED_FCLI_VERSION}" target="$FORTIFY_FCLI_INSTALL_DIR"
    local archive checksum temp_dir url checksum_url expected actual
    if [ -z "$version" ]; then
        error "FORTIFY_RECOMMENDED_FCLI_VERSION is empty."
        return 1
    fi
    command -v curl >/dev/null 2>&1 || { error "curl is required to download FCLI."; return 1; }
    command -v tar >/dev/null 2>&1 || { error "tar is required to extract FCLI."; return 1; }
    command -v sha256sum >/dev/null 2>&1 || { error "sha256sum is required to verify FCLI."; return 1; }
    temp_dir=$(mktemp -d) || return 1
    archive="$temp_dir/fcli-linux.tgz"
    checksum="$temp_dir/fcli-linux.tgz.sha256"
    url="https://github.com/fortify/fcli/releases/download/v${version}/fcli-linux.tgz"
    checksum_url="${url}.sha256"
    note "Downloading FCLI $version from the Fortify GitHub release assets."
    if ! curl -fsSL "$url" -o "$archive" || ! curl -fsSL "$checksum_url" -o "$checksum"; then
        rm -rf "$temp_dir"
        error "Could not download FCLI $version. Check network access and FORTIFY_RECOMMENDED_FCLI_VERSION."
        return 1
    fi
    expected=$(awk '{print $1; exit}' "$checksum")
    actual=$(sha256sum "$archive" | awk '{print $1; exit}')
    if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
        rm -rf "$temp_dir"
        error "FCLI checksum verification failed."
        return 1
    fi
    mkdir -p "$target" || { rm -rf "$temp_dir"; return 1; }
    tar -xzf "$archive" -C "$target" fcli fcli_completion || {
        rm -rf "$temp_dir"
        error "Could not extract FCLI into $target."
        return 1
    }
    chmod 755 "$target/fcli" 2>/dev/null || true
    rm -rf "$temp_dir"
    note "Installed FCLI $version into $target."
    if fcli_export_current_path "$target"; then
        note "Added FCLI to the current shell PATH."
    fi
    if fcli_persist_path "$target"; then
        note "Persisted the FCLI PATH handoff in $(fcli_shell_profile_path)."
    fi
    if [ -s "$(fcli_truststore_path)" ]; then
        fcli_configure_lab_trust "$(fcli_truststore_path)" || return 1
    else
        note "Generate TLS certificates before configuring fcli lab TLS trust."
    fi
}

fcli_print_command_templates() {
    local ssc_url="${SSC_URL:-https://ssc.${DOMAIN:-fortifydemo.com}}"
    local sast_url="${SCSAST_CTRL_URL:-https://sast.${DOMAIN:-fortifydemo.com}/scancentral-ctrl/}"
    cat <<EOF

SSC-first FCLI templates

  # Create a temporary SSC/FCLI session. Paste token values only when fcli asks,
  # or replace placeholders in a private shell. Do not save filled commands.
  fcli ssc session login --url "$ssc_url" --sc-sast-url "$sast_url" --token='<SSC_TOKEN_OR_PROMPT>' --client-auth-token='<SCANCENTRAL_CLIENT_AUTH_TOKEN>' --ssc-session=fortifylab

  # Inspect the intended SSC application version before any scan submission.
  fcli ssc appversion get '<APP_VERSION_NAME_OR_ID>' --ssc-session=fortifylab

  # Later scan submission starts from a prebuilt package or MBS file; this
  # readiness menu intentionally does not build sample apps or submit scans.
  fcli sc-sast scan start --file='<PACKAGE_OR_MBS_FILE>' --publish-to='<APP_VERSION_NAME_OR_ID>' --ssc-session=fortifylab

  fcli ssc session logout --ssc-session=fortifylab

FoD optional templates

  fcli fod session login --url='<FOD_URL>' --tenant='<FOD_TENANT>' --client-id='<FOD_CLIENT_ID>' --client-secret='<FOD_CLIENT_SECRET>' --fod-session=fortifylab-fod
  fcli fod release get '<FOD_RELEASE_ID_OR_NAME>' --fod-session=fortifylab-fod
  fcli fod session logout --fod-session=fortifylab-fod

EOF
}

fcli_tools_menu() {
    local choice
    while true; do
        title "Tools and FCLI readiness"
        fcli_print_status
        cat <<EOF

  1. Install or update FCLI to the recommended version
  2. Configure fcli trust for lab TLS
  3. Show FCLI status
  4. Show secret-safe command templates

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) fcli_install_or_update; press_any ;;
            2) fcli_configure_lab_trust; press_any ;;
            3) fcli_print_status; press_any ;;
            4) fcli_print_command_templates; press_any ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


