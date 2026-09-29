#!/bin/bash
# Init container for Jenkins pods in the Fortify lab (controller and agents).
#
# 1. Builds a trust bundle that holds the image's default public CAs PLUS the
#    lab root CA, so Java, git, curl, Python and Node trust https://*.<DOMAIN>
#    without losing trust in GitHub, Maven Central, or the Jenkins update
#    center. (A lab-only truststore is what broke fcli's public downloads in
#    scripts/create-certs.sh; this keeps the defaults on purpose.)
# 2. Installs fcli onto the shared tools volume (agents only), pinned and
#    checksum-verified like the wizard's host installer, and points fcli at
#    the trust bundle.
# 3. Installs Apache Maven onto the same volume (agents only), pinned and
#    SHA-512-verified from Maven Central. The agent image already ships a full
#    JDK 21 (with javac), so `mvn` runs directly in the agent container.
#
# Installed by apps/jenkins/start.sh as ConfigMap jenkins-agent-init. Every
# path can be overridden so the tests can run this script outside a pod.

set -euo pipefail

CA_FILE="${FORTIFYLAB_CA_FILE:-/fortifylab-ca/rootCA.pem}"
TRUST_DIR="${FORTIFYLAB_TRUST_DIR:-/fortifylab-trust}"
TOOLS_DIR="${FORTIFYLAB_TOOLS_DIR:-/fortifylab-tools}"
JAVA_CACERTS="${FORTIFYLAB_JAVA_CACERTS:-${JAVA_HOME:-/opt/java/openjdk}/lib/security/cacerts}"
SYSTEM_BUNDLE="${FORTIFYLAB_SYSTEM_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
TRUST_PASSWORD="${FORTIFYLAB_TRUSTSTORE_PASSWORD:-changeit}"
# auto: install fcli; manual: users install it themselves; none: trust only.
FCLI_INSTALL="${FORTIFY_JENKINS_FCLI_INSTALL:-auto}"
FCLI_VERSION="${FORTIFY_JENKINS_FCLI_VERSION:-}"
FCLI_RELEASE_BASE_URL="${FCLI_RELEASE_BASE_URL:-https://github.com/fortify/fcli/releases/download}"
# Empty skips Maven.
MAVEN_VERSION="${FORTIFY_JENKINS_MAVEN_VERSION:-}"
MAVEN_RELEASE_BASE_URL="${MAVEN_RELEASE_BASE_URL:-https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven}"

log() { printf '[fortifylab-init] %s\n' "$*"; }
warn() { printf '[fortifylab-init] WARNING: %s\n' "$*" >&2; }

build_trust() {
    local cert_dir count=0 cert
    [ -s "$CA_FILE" ] || { warn "lab root CA not found at $CA_FILE; only public CAs are trusted."; return 1; }
    mkdir -p "$TRUST_DIR"
    cp "$JAVA_CACERTS" "$TRUST_DIR/cacerts"
    chmod 0644 "$TRUST_DIR/cacerts"
    # keytool -importcert reads only the first certificate of a PEM file, and
    # a bring-your-own CA file may hold a whole chain: import each one.
    cert_dir=$(mktemp -d)
    awk -v dir="$cert_dir" '
        /-----BEGIN CERTIFICATE-----/ { n++; file = sprintf("%s/ca-%02d.pem", dir, n) }
        n { print > file }
        /-----END CERTIFICATE-----/ { close(file) }
    ' "$CA_FILE"
    for cert in "$cert_dir"/ca-*.pem; do
        [ -e "$cert" ] || continue
        count=$((count + 1))
        keytool -importcert -noprompt -alias "fortifylab-ca-$count" -file "$cert" \
            -keystore "$TRUST_DIR/cacerts" -storepass "$TRUST_PASSWORD" >/dev/null
    done
    rm -rf "$cert_dir"
    [ "$count" -gt 0 ] || { warn "no certificates found in $CA_FILE."; return 1; }
    cp "$CA_FILE" "$TRUST_DIR/rootCA.pem"
    if [ -s "$SYSTEM_BUNDLE" ]; then
        cat "$SYSTEM_BUNDLE" "$CA_FILE" >"$TRUST_DIR/ca-bundle.crt"
    else
        cp "$CA_FILE" "$TRUST_DIR/ca-bundle.crt"
    fi
    log "trust bundle ready: $count lab CA certificate(s) added to the default CAs."
}

# download_verified <url> <file> <sha256|sha512>: download url and
# url.<algorithm>, then check the hash. The checksum file may hold just the
# hash (Maven Central) or "hash  filename" (fcli releases).
download_verified() {
    local url="$1" file="$2" algorithm="$3" expected actual
    curl -fsSL --retry 3 -o "$file" "$url" || return 1
    expected=$(curl -fsSL --retry 3 "$url.$algorithm" | awk 'NF { print $1; exit }') || return 1
    actual=$("${algorithm}sum" "$file" | awk '{ print $1 }')
    [ -n "$expected" ] && [ "$expected" = "$actual" ] || return 2
}

# install_package <name> <version> <url> <algorithm> <archive-member> <bin-path>
# Installs <archive-member> of the archive at <url> as
# $TOOLS_DIR/<name>/<version>/ and links $TOOLS_DIR/bin/<command> to
# <bin-path> inside it. Each version installs once per tools volume.
install_package() {
    local name="$1" version="$2" url="$3" algorithm="$4" member="$5" bin_path="$6"
    local dest="$TOOLS_DIR/$name/$version" command tmp src rc=0
    command="$(basename "$bin_path")"
    mkdir -p "$TOOLS_DIR/bin" "$TOOLS_DIR/$name"
    if [ -e "$dest/$bin_path" ]; then
        log "$name $version already on the tools volume."
    else
        tmp=$(mktemp -d "$TOOLS_DIR/.$name-install.XXXXXX")
        log "downloading $name $version from $url"
        download_verified "$url" "$tmp/archive.tgz" "$algorithm" || rc=$?
        if [ "$rc" -eq 2 ]; then
            rm -rf "$tmp"
            warn "$name $version checksum mismatch; refusing to install it."
            return 1
        elif [ "$rc" -ne 0 ]; then
            rm -rf "$tmp"
            warn "could not download $name $version; builds can still run, or install $name manually."
            return 1
        fi
        mkdir -p "$tmp/extract"
        tar -xzf "$tmp/archive.tgz" -C "$tmp/extract" "$member"
        # A single-file member (fcli) goes into its own directory; a
        # directory member (apache-maven-X) becomes the version directory.
        if [ -d "$tmp/extract/$member" ]; then
            src="$tmp/extract/$member"
        else
            src="$tmp/pkg"
            mkdir -p "$src"
            mv "$tmp/extract/$member" "$src/"
        fi
        chmod 0755 "$src/$bin_path"
        # Rename is atomic on one filesystem, so parallel agents never run a
        # half-written tool. Losing the race to another agent is fine.
        mv -T "$src" "$dest" 2>/dev/null || log "another agent installed $name $version first."
        rm -rf "$tmp"
        log "installed $name $version."
    fi
    ln -sfn "../$name/$version/$bin_path" "$TOOLS_DIR/bin/.$command.next"
    mv -Tf "$TOOLS_DIR/bin/.$command.next" "$TOOLS_DIR/bin/$command"
}

install_fcli() {
    [ -n "$FCLI_VERSION" ] || { warn "FORTIFY_JENKINS_FCLI_VERSION is empty; fcli not installed."; return 1; }
    install_package fcli "$FCLI_VERSION" "$FCLI_RELEASE_BASE_URL/v$FCLI_VERSION/fcli-linux.tgz" sha256 fcli fcli
}

install_maven() {
    [ -n "$MAVEN_VERSION" ] || return 0
    install_package maven "$MAVEN_VERSION" \
        "$MAVEN_RELEASE_BASE_URL/$MAVEN_VERSION/apache-maven-$MAVEN_VERSION-bin.tar.gz" \
        sha512 "apache-maven-$MAVEN_VERSION" bin/mvn
}

# fcli is a native binary and ignores JAVA_TOOL_OPTIONS, so point its own
# truststore setting at the bundle. FCLI_DATA_DIR lives in the pod's trust
# volume, and the agent container gets the same FCLI_DATA_DIR.
configure_fcli_trust() {
    local fcli="$TOOLS_DIR/bin/fcli"
    [ -x "$fcli" ] || return 0
    [ -s "$TRUST_DIR/cacerts" ] || return 0
    FCLI_DATA_DIR="$TRUST_DIR/fcli-data" "$fcli" config truststore set \
        --file "$TRUST_DIR/cacerts" --type jks --password "$TRUST_PASSWORD" >/dev/null &&
        log "fcli trusts the lab CA and public CAs." ||
        warn "could not configure fcli trust."
}

main() {
    build_trust || true
    # Maven is independent of the fcli mode; the controller (none) skips it.
    [ "$FCLI_INSTALL" = none ] || install_maven || true
    case "$FCLI_INSTALL" in
        auto)
            install_fcli || true
            configure_fcli_trust
            ;;
        manual)
            mkdir -p "$TOOLS_DIR/bin"
            log "fcli install mode is manual; $TOOLS_DIR/bin is writable and on PATH."
            # Trust a copy a user installed earlier.
            configure_fcli_trust
            ;;
        none) ;;
        *) warn "unknown FORTIFY_JENKINS_FCLI_INSTALL=$FCLI_INSTALL; expected auto, manual, or none." ;;
    esac
    # Never fail the pod: builds that don't need the lab CA or fcli still run.
    return 0
}

main "$@"
