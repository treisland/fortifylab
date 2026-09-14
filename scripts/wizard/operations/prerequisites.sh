#!/usr/bin/env bash
# shellcheck shell=bash
# Module: operations/prerequisites
# Responsibility: Display, install, verify, and activate host prerequisites.
# Requires: FORTIFY_HOME_K8S; OK_MARK; WARN_MARK; title, ask, error, note,
#           press_any; refresh_registry_credentials; sudo, apt, docker, microk8s,
#           getent, awk, grep, sg, bash and the MicroK8s installer entry point.
# Exports: prereqs_menu, install_*, ensure_registry_credentials, prereq_status,
#          *_ready probes, prereqs_* summaries, fortify_group_*, ensure_active_groups,
#          prereqs_refresh_group_access.
# Side effects: Installs host packages, changes group membership, authenticates to a registry,
#               and may replace the current process to activate groups.
# Interactive: prereqs_menu and registry/group flows may prompt.

if [[ -n "${FORTIFYLAB_WIZARD_PREREQUISITES_LOADED:-}" ]]; then
    return 0
fi
FORTIFYLAB_WIZARD_PREREQUISITES_LOADED=1

prereqs_menu() {
    while true; do
        title "Install prerequisites"
        echo
        prereqs_status_table
        echo
        echo "  1. JDK 17 (apt)"
        echo "  2. Maven (apt)"
        echo "  3. Docker (apt) + docker login"
        echo "  4. mkcert (apt)"
        echo "  5. microk8s (snap) + addons (dns, ingress, nfs, dashboard, community)"
        echo "  6. All of the above"
        echo "  g. Refresh group access (microk8s/docker) now"
        echo
        echo "  r. Return"
        echo
        ask choice "Select:"

        case "$choice" in
            1) install_jdk;        prereqs_install_summary ;;
            2) install_maven;      prereqs_install_summary ;;
            3) install_docker;     prereqs_install_summary ;;
            4) install_mkcert;     prereqs_install_summary ;;
            5) install_microk8s;   prereqs_install_summary ;;
            6) install_jdk; install_maven; install_host_cli_tools; install_docker; install_mkcert; install_microk8s; prereqs_install_summary ;;
            [Gg]) prereqs_refresh_group_access ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


install_jdk()      { command -v java   &>/dev/null && note "Already installed."  || sudo apt install -y openjdk-17-jre-headless; }
install_maven()    { command -v mvn    &>/dev/null && note "Already installed."  || sudo apt install -y maven; }
install_mkcert()   { command -v mkcert &>/dev/null && note "Already installed."  || sudo apt install -y mkcert; }
install_host_cli_tools() {
    local packages=()
    command -v openssl >/dev/null 2>&1 || packages+=("openssl")
    command -v curl >/dev/null 2>&1 || packages+=("curl")
    command -v envsubst >/dev/null 2>&1 || packages+=("gettext-base")
    command -v sg >/dev/null 2>&1 || command -v newgrp >/dev/null 2>&1 || packages+=("util-linux-extra")
    if [ "${#packages[@]}" -eq 0 ]; then
        note "Already installed."
        return 0
    fi
    sudo apt install -y "${packages[@]}"
}
install_docker()   {
    install_host_cli_tools
    if command -v docker &>/dev/null; then
        note "Already installed."
    else
        sudo apt install -y docker.io
    fi
    local target_user
    target_user="${SUDO_USER:-$(id -un)}"
    sudo usermod -aG docker "$target_user"
    if ! [ -f "$HOME/.docker/config.json" ]; then
        note "Logging into Docker Hub (needed to pull Fortify images)..."
        docker login
    fi
    ensure_active_groups
}

ensure_registry_credentials() {
    case "$1" in
        mysql|postgresql|ssc|lim|sast|dast)
            refresh_registry_credentials
            ;;
    esac
}
install_microk8s() {
    install_host_cli_tools
    if command -v microk8s &>/dev/null; then
        note "Already installed."
    else
        bash "$FORTIFY_HOME_K8S/scripts/install_microk8s.sh"
    fi
    ensure_active_groups
    if microk8s_access_ready; then
        note "MicroK8s access is active in this shell."
    fi
}

prereq_status() {
    if "$@"; then
        printf '%s ready' "$OK_MARK"
    else
        printf '%s needs attention' "$WARN_MARK"
    fi
}

docker_ready() {
    command -v docker >/dev/null 2>&1 || return 1
    [ -s "$HOME/.docker/config.json" ] || return 1
}

host_cli_tools_ready() {
    local command
    for command in openssl curl envsubst; do
        command -v "$command" >/dev/null 2>&1 || return 1
    done
    command -v sg >/dev/null 2>&1 || command -v newgrp >/dev/null 2>&1 || return 1
}

mkcert_ready() { command -v mkcert >/dev/null 2>&1; }
java_ready() { command -v java >/dev/null 2>&1 && command -v keytool >/dev/null 2>&1; }
maven_ready() { command -v mvn >/dev/null 2>&1; }

microk8s_access_ready() {
    command -v microk8s >/dev/null 2>&1 || return 1
    id -nG | grep -qw microk8s || return 1
    microk8s status --wait-ready >/dev/null 2>&1 || return 1
}

prereqs_status_table() {
    printf '  %-24s %s\n' "JDK 17" "$(prereq_status java_ready)"
    printf '  %-24s %s\n' "Maven" "$(prereq_status maven_ready)"
    printf '  %-24s %s\n' "Host CLI helpers" "$(prereq_status host_cli_tools_ready)"
    printf '  %-24s %s\n' "Docker + login" "$(prereq_status docker_ready)"
    printf '  %-24s %s\n' "mkcert" "$(prereq_status mkcert_ready)"
    printf '  %-24s %s\n' "MicroK8s access" "$(prereq_status microk8s_access_ready)"
}

prereqs_ready_count() {
    local ready=0
    java_ready && ready=$((ready + 1))
    maven_ready && ready=$((ready + 1))
    host_cli_tools_ready && ready=$((ready + 1))
    docker_ready && ready=$((ready + 1))
    mkcert_ready && ready=$((ready + 1))
    microk8s_access_ready && ready=$((ready + 1))
    printf '%s\n' "$ready"
}

prereqs_install_summary() {
    local ready pending
    ready=$(prereqs_ready_count)
    printf '\n'
    note "Host prerequisites: $ready/6 ready."
    if [ "$ready" -eq 6 ]; then
        note "All prerequisite indicators are complete."
    else
        pending="$(fortify_groups_pending_activation)"
        if [ -n "$pending" ]; then
            note "Next missing: group access in this shell for $(printf '%s' "$pending" | tr '\n' ' ')."
            note "Choose g to refresh group access now, or start a new shell."
        fi
    fi
    press_any
}

# fortify_group_member <group> — true if $USER is listed as a supplementary
# member of <group> in the system group database (independent of whether
# that membership is active in *this* process's session).
fortify_group_member() {
    local group="$1" current_user
    current_user="$(id -un)"
    getent group "$group" 2>/dev/null | awk -F: -v u="$current_user" '
        {
            n = split($4, a, ",")
            for (i = 1; i <= n; i++) if (a[i] == u) found = 1
        }
        END { exit !found }
    '
}

# fortify_group_active <group> — true if <group> is active in this process's
# current supplementary group list (i.e. usable without re-login/newgrp/sg).
fortify_group_active() {
    id -nG | tr ' ' '\n' | grep -qx "$1"
}

# Groups the user is entitled to (per /etc/group) but that are not yet
# active in this shell — the gap that forces a manual `newgrp`/relaunch.
# Only considers groups for tooling that is actually installed.
fortify_groups_pending_activation() {
    local group
    for group in microk8s docker; do
        command -v "$group" >/dev/null 2>&1 || continue
        fortify_group_member "$group" || continue
        fortify_group_active "$group" || printf '%s\n' "$group"
    done
}

# ensure_active_groups — transparently activates any pending microk8s/docker
# group membership by re-executing the wizard through chained `sg` calls, so
# the user never has to notice a "needs attention" status or run a command
# by hand. No-op if everything is already active. Guarded against re-exec
# loops via FORTIFY_GROUP_REEXEC, in case `sg` doesn't actually grant access
# (e.g. no controlling TTY).
ensure_active_groups() {
    local pending group restart_command sg_command
    pending="$(fortify_groups_pending_activation)"
    [ -n "$pending" ] || return 0

    if [ -n "${FORTIFY_GROUP_REEXEC:-}" ]; then
        note "Still missing group access for: $(printf '%s' "$pending" | tr '\n' ' ')"
        note "Start a new shell (or log out and back in), then relaunch the wizard."
        return 1
    fi

    if ! command -v sg >/dev/null 2>&1; then
        if command -v apt >/dev/null 2>&1; then
            note "Installing util-linux-extra so the wizard can refresh group access automatically..."
            sudo apt install -y util-linux-extra || return 1
        fi
    fi

    if ! command -v sg >/dev/null 2>&1; then
        error "Could not find sg to refresh group access automatically."
        note "Install util-linux-extra, then relaunch the wizard."
        note "If newgrp is available, run this in your shell first (one group per newgrp):"
        while IFS= read -r group; do
            note "  newgrp $group"
        done <<< "$pending"
        return 1
    fi

    note "Activating group access for: $(printf '%s' "$pending" | tr '\n' ' ')..."
    printf -v restart_command '%q --accept-lab-use' "$FORTIFY_HOME_K8S/start_wizard.sh"
    sg_command="$restart_command"
    while IFS= read -r group; do
        printf -v sg_command 'sg %q -c %q' "$group" "$sg_command"
    done <<< "$pending"
    export FORTIFY_GROUP_REEXEC=1
    exec bash -c "$sg_command"
}

# Interactive wrapper around ensure_active_groups for the prerequisites menu:
# gives explicit feedback either way, since a silent no-op would look like
# the keypress did nothing.
prereqs_refresh_group_access() {
    if [ -z "$(fortify_groups_pending_activation)" ]; then
        note "Group access is already active in this shell."
        press_any
        return 0
    fi
    ensure_active_groups
    # Only reached if ensure_active_groups couldn't exec (no sg, or already
    # re-exec'd once without success) — a successful activation replaces
    # this process and never returns here.
    press_any
}
