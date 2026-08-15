#!/usr/bin/env bash

# TLS configuration and validation helpers. These functions never print
# private key contents; checks use OpenSSL metadata and public keys only.

fortify_tls_mode() {
    local mode="${FORTIFY_TLS_MODE:-mkcert}"
    mode="${mode,,}"
    case "$mode" in
        mkcert|byo) printf '%s\n' "$mode" ;;
        *)
            printf 'Invalid FORTIFY_TLS_MODE: %s\n' "${FORTIFY_TLS_MODE:-<unset>}" >&2
            printf 'Use mkcert or byo.\n' >&2
            return 1
            ;;
    esac
}

fortify_tls_lab_hosts() {
    printf '%s\n' \
        "${SSC:-ssc.${DOMAIN:?DOMAIN is required}}" \
        "${LIM:-lim.${DOMAIN:?DOMAIN is required}}" \
        "${SCSAST:-sast.${DOMAIN:?DOMAIN is required}}" \
        "${SCDAST:-dast.${DOMAIN:?DOMAIN is required}}" \
        "dashboard.${DOMAIN:?DOMAIN is required}" |
        awk 'NF && !seen[$0]++'
}

fortify_tls_require_file() {
    local label="$1" path="${2:-}"
    if [ -z "$path" ]; then
        printf 'Missing %s path.\n' "$label" >&2
        return 1
    fi
    if [ ! -s "$path" ]; then
        printf '%s file not found or empty: %s\n' "$label" "$path" >&2
        return 1
    fi
}

fortify_tls_validate_cert_file() {
    local label="$1" path="$2"
    fortify_tls_require_file "$label" "$path" || return 1
    openssl x509 -in "$path" -noout >/dev/null 2>&1 || {
        printf '%s is not a readable PEM certificate: %s\n' "$label" "$path" >&2
        return 1
    }
}

fortify_tls_validate_key_file() {
    local label="$1" path="$2"
    fortify_tls_require_file "$label" "$path" || return 1
    openssl pkey -in "$path" -noout >/dev/null 2>&1 || {
        printf '%s is not a readable PEM private key: %s\n' "$label" "$path" >&2
        return 1
    }
}

fortify_tls_cert_key_match() {
    local cert="$1" key="$2" cert_pub key_pub
    cert_pub=$(openssl x509 -in "$cert" -pubkey -noout 2>/dev/null | openssl sha256 2>/dev/null) || return 1
    key_pub=$(openssl pkey -in "$key" -pubout 2>/dev/null | openssl sha256 2>/dev/null) || return 1
    [ -n "$cert_pub" ] && [ "$cert_pub" = "$key_pub" ]
}

fortify_tls_host_matches_pattern() {
    local host="$1" pattern="$2" suffix remainder
    [ "$host" = "$pattern" ] && return 0
    case "$pattern" in
        "*."*)
            suffix="${pattern#*.}"
            case "$host" in
                *."$suffix")
                    remainder="${host%.$suffix}"
                    [ -n "$remainder" ] && [[ "$remainder" != *.* ]]
                    return
                    ;;
            esac
            ;;
    esac
    return 1
}

fortify_tls_cert_covers_host() {
    local cert="$1" host="$2" san dns
    san=$(openssl x509 -in "$cert" -noout -ext subjectAltName 2>/dev/null || true)
    [ -n "$san" ] || return 1
    while IFS= read -r dns; do
        dns="${dns#DNS:}"
        dns="${dns%%,*}"
        dns="${dns#"${dns%%[![:space:]]*}"}"
        dns="${dns%"${dns##*[![:space:]]}"}"
        fortify_tls_host_matches_pattern "$host" "$dns" && return 0
    done < <(printf '%s\n' "$san" | grep -oE 'DNS:[^,[:space:]]+')
    return 1
}

fortify_tls_validate_cert_hosts() {
    local cert="$1" host missing=0
    while IFS= read -r host; do
        [ -n "$host" ] || continue
        if ! fortify_tls_cert_covers_host "$cert" "$host"; then
            printf 'TLS certificate SAN does not cover required hostname: %s\n' "$host" >&2
            missing=1
        fi
    done < <(fortify_tls_lab_hosts)
    [ "$missing" -eq 0 ]
}

fortify_tls_validate_byo_inputs() {
    fortify_tls_validate_cert_file "FORTIFY_BYO_TLS_CERT" "${FORTIFY_BYO_TLS_CERT:-}" || return 1
    fortify_tls_validate_key_file "FORTIFY_BYO_TLS_KEY" "${FORTIFY_BYO_TLS_KEY:-}" || return 1
    fortify_tls_validate_cert_file "FORTIFY_BYO_TLS_CA_CERT" "${FORTIFY_BYO_TLS_CA_CERT:-}" || return 1
    fortify_tls_cert_key_match "$FORTIFY_BYO_TLS_CERT" "$FORTIFY_BYO_TLS_KEY" || {
        printf 'FORTIFY_BYO_TLS_CERT and FORTIFY_BYO_TLS_KEY do not match.\n' >&2
        return 1
    }
    fortify_tls_validate_cert_hosts "$FORTIFY_BYO_TLS_CERT"
}
