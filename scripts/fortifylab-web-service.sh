#!/usr/bin/env bash
set -euo pipefail

# Runtime wrapper for the optional fortifylab-web service. It reads .env from
# the clone and starts the Python web console without printing tokens.
ROOT="${FORTIFY_HOME_K8S:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
if [ -f "$ROOT/.env" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.env"
fi

bind="${FORTIFY_WEB_BIND:-127.0.0.1}"
port="${FORTIFY_WEB_PORT:-8443}"
token_file="${FORTIFY_WEB_TOKEN_FILE:-$ROOT/.fortifylab/web-token}"
tls_cert="${FORTIFY_WEB_TLS_CERT:-${SERVER_CERT:-$ROOT/certs/tls.crt}}"
tls_key="${FORTIFY_WEB_TLS_KEY:-${SERVER_KEY:-$ROOT/certs/tls.key}}"
lab_host="${LAB_HOST:-${DOMAIN:+lab.$DOMAIN}}"
lab_url="${LAB_URL:-}"

args=(web serve --bind "$bind" --port "$port")
if [ "${FORTIFY_WEB_ALLOW_LAN:-false}" = "true" ]; then
  args+=(--allow-lan)
fi
if [ -s "$token_file" ]; then
  args+=(--token-file "$token_file")
fi
if [ "${FORTIFY_WEB_ENABLE_ACTIONS:-false}" = "true" ]; then
  args+=(--enable-actions)
fi
if [ -n "$tls_cert" ] || [ -n "$tls_key" ]; then
  args+=(--tls-cert "$tls_cert" --tls-key "$tls_key")
fi
if [ -n "$lab_host" ]; then
  args+=(--lab-host "$lab_host")
fi
if [ -n "$lab_url" ]; then
  args+=(--lab-url "$lab_url")
fi

exec "$ROOT/bin/fortifylab" "${args[@]}"
