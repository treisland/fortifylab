#!/usr/bin/env bash
# shellcheck shell=bash

# ============================================================
# Integrations — optional CI tools that sit beside the Fortify lab.
# Kept out of the app registry and guided deployment on purpose: full-lab
# lifecycle actions and deployment profiles never touch them.
# ============================================================

jenkins_integration_env() {
    # shellcheck source=../../apps/jenkins/common.sh
    source "$FORTIFY_HOME_K8S/apps/jenkins/common.sh"
    jenkins_apply_defaults
}

jenkins_integration_release_line() {
    [ -n "${HELM:-}" ] || return 1
    # shellcheck disable=SC2086
    $HELM -n "$NAMESPACE" list --all -o json 2>/dev/null | python3 -c '
import json, sys
try:
    releases = json.load(sys.stdin) or []
except json.JSONDecodeError:
    releases = []
for release in releases:
    if release.get("name") == "jenkins":
        print(f"{release.get(\"chart\", \"?\")} (Jenkins {release.get(\"app_version\", \"?\")}, {release.get(\"status\", \"?\")})")
        break
'
}

jenkins_integration_state() {
    local release
    cluster_reachable || { printf 'unknown (cluster unreachable)\n'; return 0; }
    release=$(jenkins_integration_release_line 2>/dev/null || true)
    if [ -z "$release" ]; then
        printf 'not deployed\n'
    elif ( source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"; health_jenkins_probe ) >/dev/null 2>&1; then
        printf 'running\n'
    elif workload_ready "$NAMESPACE" statefulset jenkins; then
        printf 'starting (login page not reachable yet)\n'
    else
        printf 'stopped or starting\n'
    fi
}

jenkins_integration_status() {
    local release
    jenkins_integration_env
    section "Jenkins"
    printf '  State:            %s\n' "$(jenkins_integration_state)"
    release=$(jenkins_integration_release_line 2>/dev/null || true)
    printf '  Helm release:     %s\n' "${release:-none}"
    printf '  Pinned chart:     %s (controller %s)\n' "$FORTIFY_JENKINS_CHART_VERSION" "$FORTIFY_JENKINS_IMAGE_TAG"
    printf '  URL:              %s\n' "$JENKINS_URL"
    printf '  Admin user:       %s\n' "$JENKINS_ADMIN_USER"
    printf '  Admin password:   %s\n' "$([ -n "${JENKINS_ADMIN_PASSWORD:-}" ] && printf 'JENKINS_ADMIN_PASSWORD in .env' || printf 'DEFAULT_PASS in .env')"
    printf '  Agents:           label "fortifylab", up to %s at once, trust the lab root CA\n' "$JENKINS_AGENT_MAX"
    printf '  fcli on agents:   %s (version %s)\n' "$FORTIFY_JENKINS_FCLI_INSTALL" "$FORTIFY_JENKINS_FCLI_VERSION"
}

jenkins_integration_access_help() {
    jenkins_integration_env
    cat <<EOF

Open Jenkins
  URL:   $JENKINS_URL
  Login: $JENKINS_ADMIN_USER / the password in .env (JENKINS_ADMIN_PASSWORD, or DEFAULT_PASS)

  Your browser machine must resolve $JENKINS to the lab node. Add it to the
  client's /etc/hosts or DNS. More tools -> Advanced setup and configuration
  -> Configure -> DNS prints the full host line.

Use the lab-aware agent in a pipeline
  pipeline {
    agent { label 'fortifylab' }
    stages {
      stage('fcli') { steps { sh 'fcli --version' } }
    }
  }

  Agents trust the lab root CA as well as public CAs (Java, git, curl,
  Python, Node, and fcli). In manual fcli mode, install fcli into
  /fortifylab-tools/bin; see docs/operations/jenkins.md.
EOF
}

jenkins_integration_start() {
    jenkins_integration_env
    run_app_scripts "apps/jenkins/start.sh" || return $?
    (
        source "$FORTIFY_HOME_K8S/scripts/lib/dependency-health.sh"
        health_jenkins_ready
    ) || {
        error "Jenkins did not become ready. Check: $KUBECTL -n $NAMESPACE get pods -l app.kubernetes.io/instance=jenkins"
        return 1
    }
    note "Jenkins is ready at $JENKINS_URL"
}

jenkins_integration_destroy() {
    local destroy_data=0
    confirm "Remove Jenkins from the lab?" || { note "Jenkins was not removed."; return 0; }
    if confirm "Also delete Jenkins jobs, build history, and agent tools? This cannot be undone."; then
        destroy_data=1
    fi
    JENKINS_DESTROY_DATA="$destroy_data" run_app_scripts "apps/jenkins/destroy.sh"
}

jenkins_integration_menu() {
    local choice
    while true; do
        title "Integrations: Jenkins CI"
        jenkins_integration_status
        cat <<'EOF'

  1. Start / upgrade Jenkins
  2. Stop Jenkins (keeps data)
  3. Remove Jenkins
  4. How to open Jenkins and use the lab agent

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) jenkins_integration_start; press_any ;;
            2) run_app_scripts "apps/jenkins/stop.sh"; press_any ;;
            3) jenkins_integration_destroy; press_any ;;
            4) jenkins_integration_access_help; press_any ;;
            [Rr]|"") return 0 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

integrations_menu() {
    local choice
    while true; do
        title "Integrations"
        cat <<'EOF'

Optional CI tools that use the lab domain and TLS certificate. They are not
part of the Fortify deployment, lab lifecycle controls, or Flight Plans.

  1. Jenkins CI

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) jenkins_integration_menu ;;
            [Rr]|"") return 0 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}
