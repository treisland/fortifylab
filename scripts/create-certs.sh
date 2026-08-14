#!/bin/bash
#
# CREATE CERTIFICATES
# -----------------------------------
#
# Idempotent clean rebuild of every cert artifact the lab needs.
#
# Outputs (all under $FORTIFY_CERTS):
#   rootCA.pem                      — mkcert root CA or operator-provided CA chain
#   rootCA-key.pem                  — mkcert root key (mkcert mode only)
#   rootCA.pfx                      — LIM signing/server-compatible PKCS12
#   tls.crt, tls.key                — leaf cert for $DOMAIN (nginx ingress + SSC)
#   keystore.p12                    — PKCS12 of the leaf
#   keystore.jks                    — JKS form for SSC's HTTPS connector
#   truststore                      — JVM truststore: leaf + mkcert rootCA
#                                     + Amazon Root CA 1 (for update.fortify.com)
#   update.fortify.com.crt          — leaf cert for the rulepack update server
#
# TLS modes:
#   FORTIFY_TLS_MODE=mkcert (default) creates a lab-local mkcert CA + wildcard.
#   FORTIFY_TLS_MODE=byo validates FORTIFY_BYO_TLS_CERT, FORTIFY_BYO_TLS_KEY,
#   and FORTIFY_BYO_TLS_CA_CERT, then copies them into the generated layout.
#
# Read-only consumers (create-secrets.sh, app start.sh files) read these
# directly from $FORTIFY_CERTS — there is no separate copy in secrets/generated/.
#========================================================

set -euo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    export FORTIFY_HOME_K8S
fi

source "$FORTIFY_HOME_K8S/.env"
source "$FORTIFY_HOME_K8S/scripts/lib/tls.sh"

TLS_MODE="$(fortify_tls_mode)"
BYO_STAGING_DIR=""
CA_IMPORT_DIR=""
if [ "$TLS_MODE" = byo ]; then
  fortify_tls_validate_byo_inputs
  BYO_STAGING_DIR="$(mktemp -d)"
  trap '[ -z "${BYO_STAGING_DIR:-}" ] || rm -rf "$BYO_STAGING_DIR"' EXIT
  cp "$FORTIFY_BYO_TLS_CERT" "$BYO_STAGING_DIR/tls.crt"
  cp "$FORTIFY_BYO_TLS_KEY" "$BYO_STAGING_DIR/tls.key"
  cp "$FORTIFY_BYO_TLS_CA_CERT" "$BYO_STAGING_DIR/rootCA.pem"
fi


#--------------------------
# SECTION: TOOLING
#--------------------------

# mkcert stores its CA at $HOME/.local/share/mkcert/ — running this script
# under sudo would create a *different* CA owned by root and silently
# rotate the lab's trust anchor. Refuse to do that.
if [ "$(id -u)" -eq 0 ] || [ -n "${SUDO_USER:-}" ]; then
  echo "❌ Do not run create-certs.sh as root or via sudo."
  if [ "$TLS_MODE" = mkcert ]; then
    echo "   mkcert is per-user; sudo would create a new CA at /root/... and"
    echo "   invalidate every cert the lab has issued. Run as your normal user;"
    echo "   mkcert will escalate privileges internally for the system trust"
    echo "   store install."
  else
    echo "   Run as your normal user so generated cert artifacts remain writable"
    echo "   and protected private-key material does not become root-owned."
  fi
  exit 1
fi

if [ "$TLS_MODE" = mkcert ] && ! command -v mkcert >/dev/null; then
  sudo apt install mkcert -y
fi
if ! command -v keytool >/dev/null; then
  echo "❌ keytool not found — install a JDK (e.g. openjdk-17-jre-headless)."
  exit 1
fi

if [ "$TLS_MODE" = mkcert ]; then
  # Install mkcert's CA into the system trust store (idempotent).
  mkcert -install
fi


#--------------------------
# SECTION: CLEAN REBUILD OF $FORTIFY_CERTS
#--------------------------

mkdir -p "$FORTIFY_CERTS"
# Wipe everything we own; mkcert's CAROOT (in $HOME) is untouched.
rm -f "$FORTIFY_CERTS"/*.pem \
      "$FORTIFY_CERTS"/*.key \
      "$FORTIFY_CERTS"/*.crt \
      "$FORTIFY_CERTS"/*.pfx \
      "$FORTIFY_CERTS"/*.p12 \
      "$FORTIFY_CERTS"/*.jks \
      "$FORTIFY_CERTS/truststore"

if [ "$TLS_MODE" = mkcert ]; then
  # Pull mkcert's root CA into $FORTIFY_CERTS so other scripts have a stable path.
  CAROOT="$(mkcert -CAROOT)"
  cp "$CAROOT/rootCA.pem"     "$ROOTCA_CERT"
  cp "$CAROOT/rootCA-key.pem" "$ROOTCA_KEY"
else
  CAROOT="bring-your-own"
  cp "$BYO_STAGING_DIR/rootCA.pem" "$ROOTCA_CERT"
fi


#--------------------------
# SECTION: LEAF CERT FOR $DOMAIN
#--------------------------

if [ "$TLS_MODE" = mkcert ]; then
  # Leaf wildcard for *.$DOMAIN (covers ssc.$DOMAIN, lim.$DOMAIN, etc.).
  mkcert -key-file "$SERVER_KEY" -cert-file "$SERVER_CERT" "$DOMAIN" "*.$DOMAIN"
else
  cp "$BYO_STAGING_DIR/tls.crt" "$SERVER_CERT"
  cp "$BYO_STAGING_DIR/tls.key" "$SERVER_KEY"
fi


#--------------------------
# SECTION: PFX / KEYSTORE / JKS
#--------------------------
# -legacy uses RC2-40/SHA-1 which .NET on Linux supports;
# OpenSSL 3.x default is AES-256-CBC which .NET cannot read.

# mkcert mode preserves the historical rootCA PFX for LIM. BYO mode uses the
# supplied leaf/key as the PFX because public CA private keys are not available.
if [ "$TLS_MODE" = mkcert ]; then
  openssl pkcs12 -export -legacy -out "$ROOTCA_PFX" \
      -inkey "$ROOTCA_KEY" -in "$ROOTCA_CERT" \
      -password pass:"$DEFAULT_PASS"
else
  openssl pkcs12 -export -legacy -out "$ROOTCA_PFX" \
      -inkey "$SERVER_KEY" -in "$SERVER_CERT" -certfile "$ROOTCA_CERT" \
      -password pass:"$DEFAULT_PASS"
fi

# Leaf in PKCS12 (intermediate format for the JKS keystore).
openssl pkcs12 -export -legacy -name "$DEFAULT_ALIAS" \
    -inkey "$SERVER_KEY" -in "$SERVER_CERT" \
    -out "$KEYSTORE" -password pass:"$DEFAULT_PASS"

# Leaf in JKS (SSC HTTPS connector).
keytool -importkeystore -alias "$DEFAULT_ALIAS" \
    -srckeystore "$KEYSTORE" -srcstoretype pkcs12 \
    -srcstorepass "$DEFAULT_PASS" \
    -destkeystore "$JVM_KEYSTORE" -deststorepass "$DEFAULT_PASS"


#--------------------------
# SECTION: TRUSTSTORE
#--------------------------
# Java PKIX needs CA certs (not leaves) as trust anchors. We import:
#   1. mkcert rootCA   — covers every cert we issue for $DOMAIN
#   2. update.fortify.com root CA — covers rulepack updates across leaf rotations

# Seed the truststore with the leaf (lets keytool initialize the file).
keytool -importkeystore -alias "$DEFAULT_ALIAS" \
    -srckeystore "$KEYSTORE" -srcstoretype pkcs12 -srcstorepass "$DEFAULT_PASS" \
    -destkeystore "$TRUSTSTORE" -deststorepass "$DEFAULT_PASS"

# Import the lab CA or BYO CA bundle so SSC can validate served lab certs.
CA_IMPORT_DIR="$(mktemp -d)"
awk -v dir="$CA_IMPORT_DIR" '
    /-----BEGIN CERTIFICATE-----/ { n++; file=sprintf("%s/ca-%02d.pem", dir, n) }
    n > 0 { print > file }
    /-----END CERTIFICATE-----/ { close(file) }
' "$ROOTCA_CERT"
ca_index=0
for ca_file in "$CA_IMPORT_DIR"/*.pem; do
  [ -s "$ca_file" ] || continue
  ca_index=$((ca_index + 1))
  keytool -import -alias "lab-tls-ca-$ca_index" -file "$ca_file" \
      -keystore "$TRUSTSTORE" -storepass "$DEFAULT_PASS" -noprompt
done
[ "$ca_index" -gt 0 ] || { echo "❌ No CA certificates found in $ROOTCA_CERT."; exit 1; }

# Pull the full chain from update.fortify.com (used by SSC for rulepack updates)
# and import the root CA — durable across leaf rotations.
UPDATE_CHAIN="$(mktemp)"
trap 'rm -f "$UPDATE_CHAIN" "${ROOT_CA:-}"; [ -z "${BYO_STAGING_DIR:-}" ] || rm -rf "$BYO_STAGING_DIR"; [ -z "${CA_IMPORT_DIR:-}" ] || rm -rf "$CA_IMPORT_DIR"' EXIT
openssl s_client -servername "$FORTIFY_RULES_DOMAIN" \
    -connect "$FORTIFY_RULES_DOMAIN":443 -showcerts </dev/null 2>/dev/null \
  | awk '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/' > "$UPDATE_CHAIN"

# Save the leaf for reference / debugging.
awk '/-----BEGIN CERTIFICATE-----/{n++} n==1' "$UPDATE_CHAIN" \
  | openssl x509 -text > "$FORTIFY_RULES_CERT"

# Extract the last cert in the chain (root CA) and import.
ROOT_CA="$(mktemp)"
awk -v last="$(grep -c '^-----BEGIN CERTIFICATE-----' "$UPDATE_CHAIN")" '
    /-----BEGIN CERTIFICATE-----/{c++}
    c==last' "$UPDATE_CHAIN" > "$ROOT_CA"
keytool -import -alias update-fortify-root-ca -file "$ROOT_CA" \
    -keystore "$TRUSTSTORE" -storepass "$DEFAULT_PASS" -noprompt


echo
echo "✅ Certs rebuilt in $FORTIFY_CERTS"
echo "   TLS mode: $TLS_MODE"
if [ "$TLS_MODE" = mkcert ]; then
  echo "   mkcert CAROOT: $CAROOT"
else
  echo "   BYO cert/key validated for configured lab hostnames."
fi
echo "   Run scripts/create-secrets.sh next to materialize k8s Secrets."
