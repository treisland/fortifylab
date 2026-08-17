#!/usr/bin/env bash
# shellcheck shell=bash

# ============================================================
# First-time welcome
# ============================================================

fortifylab_state_path() {
    local state_root
    if [ -n "${XDG_STATE_HOME:-}" ]; then
        state_root="$XDG_STATE_HOME"
    else
        state_root="${HOME:?HOME is required}/.local/state"
    fi
    printf '%s/fortify-lab/%s\n' "$state_root" "$1"
}

fortifylab_status_word() {
    case "$1" in
        ok) printf '%s\n' "${GREEN}ready${RESET}" ;;
        warn) printf '%s\n' "${YELLOW}attention needed${RESET}" ;;
        *) printf '%s\n' "${DIM}unknown${RESET}" ;;
    esac
}

fortifylab_welcome_intro() {
    fortify_lab_welcome_banner
    cat <<'EOF'

Welcome. Fortify Lab builds a local, ready-to-scan Fortify training lab on
MicroK8s so you can learn the product flow, run scans, and reset the
infrastructure without designing a production platform first.

Recommended path:
  1. Review host requirements and license files.
  2. Choose the deployment profile you actually want to run.
  3. Let Guided deployment install, verify, and wait for each component.
  4. Open deployed URLs, retrieve credentials deliberately, and run a first scan.

Core components:
  - SSC stores results and manages application security data.
  - ScanCentral SAST provides controller, work platform, and sensors for SAST.
  - ScanCentral DAST uses LIM and WebInspect licensing for DAST scans.
  - The Kubernetes Dashboard helps inspect pods, logs, and cluster state.
EOF
}

fortifylab_welcome_warnings() {
    cat <<'EOF'
Before you begin:
  - Run this wizard as your normal user, not with sudo.
  - This is a lab and training environment, not a production architecture.
  - Use lab-only data, credentials, and scan targets.
  - Sample applications, when installed, are intentionally vulnerable.
  - DAST workflows require ScanCentral DAST and WebInspect licenses in LIM.
EOF
}

fortifylab_license_input_path() {
    if [ -n "${FORTIFY_LICENSE_FILE:-}" ]; then
        printf '%s\n' "$FORTIFY_LICENSE_FILE"
    else
        printf '%s/secrets/input/fortify.license\n' "$FORTIFY_HOME_K8S"
    fi
}

fortifylab_welcome_locations() {
    local log_file diagnostics_dir
    log_file="$(fortify_wizard_log_file 2>/dev/null || fortifylab_state_path wizard.log)"
    diagnostics_dir="$(fortifylab_state_path diagnostics)"
    cat <<EOF
Helpful locations:
  - Repository:      $FORTIFY_HOME_K8S
  - Environment:     $ENV_FILE
  - Env backups:     $ENV_BACKUP_DIR
  - License input:   $(fortifylab_license_input_path)
  - TLS files:       $FORTIFY_HOME_K8S/certs
  - Wizard log:      $log_file
  - Diagnostics:     $diagnostics_dir
EOF
}

fortifylab_welcome_snapshot() {
    local env_status license_status docker_status microk8s_status domain profile
    [ -f "$ENV_FILE" ] && env_status=ok || env_status=warn
    if ( source "$FORTIFY_HOME_K8S/scripts/lib/fortify-license.sh" && fortify_resolve_license_file >/dev/null ) 2>/dev/null; then
        license_status=ok
    else
        license_status=warn
    fi
    command -v docker >/dev/null 2>&1 && docker_status=ok || docker_status=warn
    command -v microk8s >/dev/null 2>&1 && microk8s_status=ok || microk8s_status=warn
    domain="${DOMAIN:-<unset>}"
    profile="${GUIDED_DEPLOYMENT_PROFILE_LABEL:-$(guided_profile_label "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}")}"

    cat <<EOF
Quick environment snapshot:
  - .env:            $(fortifylab_status_word "$env_status")
  - License:         $(fortifylab_status_word "$license_status")
  - Docker:          $(fortifylab_status_word "$docker_status")
  - MicroK8s:        $(fortifylab_status_word "$microk8s_status")
  - Domain:          $domain
  - Profile:         $profile
EOF
}

fortifylab_first_time_welcome_content() {
    fortifylab_welcome_intro
    printf '\n'
    fortifylab_welcome_warnings
    printf '\n'
    fortifylab_welcome_locations
    printf '\n'
    fortifylab_welcome_snapshot
}

fortifylab_first_time_welcome_menu() {
    [ "${FORTIFY_SKIP_WELCOME:-0}" = "1" ] && return 0
    [ -t 0 ] && [ -t 1 ] || return 0

    title "Welcome to FortifyLab"
    fortifylab_first_time_welcome_content
    printf '\nThe main menu includes Initial setup and readiness as the recommended next step.\n'
    press_any
}


# ============================================================
# Main menu
# ============================================================

main_menu() {
    while true; do
        title "Fortify Lab"
        fortify_lab_menu_banner
        section "Status"
        printf '  %s\n' "$(status_prereqs)"
        printf '  %s\n' "$(status_license)"
        printf '  %s\n' "$(status_cluster)"
        status_user

        section "Deploy"
        echo "   0. Initial setup and readiness"
        echo "   1. Guided deployment (recommended)"
        echo "   2. Express deployment"
        echo "   3. Resume or repair deployment"
        echo "   4. Flight Plans and upgrades"
        echo "   5. Manage individual components (expert)"
        echo "   6. Sample applications"
        echo "   7. Kubernetes Dashboard access"

        section "Diagnostics and advanced"
        echo "   8. Diagnostics / live status"
        echo "   9. Advanced setup and configuration"

        section "Operations"
        echo "  10. Lab lifecycle controls"
        echo "  11. Stream logs (all pods)"
        echo "  12. Cluster snapshot"
        echo "  13. Tail one pod"
        echo "  14. URLs & credentials"
        echo "  15. Tools and FCLI readiness"
        echo "  16. Runbook Library"
        echo "  17. Configuration editor"

        section "Learn"
        echo "  18. Help Center / Fortify Knowledge Center"
        echo "  19. Operational guidance and troubleshooting"
        echo "  20. View wizard log"

        echo
        echo "   q. Quit"
        echo
        ask choice "Select:"

        case "$choice" in
            0)  setup_menu ;;
            1)  guided_deployment_menu ;;
            2)  deploy_from_scratch ;;
            3)  resume_repair ;;
            4)  versions_menu ;;
            5)  apps_menu ;;
            6)  sample_apps_menu ;;
            7)  dashboard_access_menu ;;
            8)  live_status ;;
            9)  advanced_menu ;;
           10)  lab_lifecycle_menu ;;
           11)  stream_logs ;;
           12)  cluster_status ;;
           13)  logs_menu ;;
           14)  urls_creds ;;
           15)  fcli_tools_menu ;;
           16)  runbooks_menu ;;
           17)  edit_env ;;
           18)  help_center ;;
           19)  operational_guidance_menu ;;
           20)  wizard_log_viewer ;;
            [Qq]) clear; exit 0 ;;
            *)   error "Invalid choice"; sleep 1 ;;
        esac
    done
}
