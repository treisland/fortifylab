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

    while true; do
        title "Welcome to FortifyLab"
        fortifylab_first_time_welcome_content
        section "Next steps"
        echo "   1. Start guided setup"
        echo "   2. Review requirements"
        echo "   3. Choose deployment profile"
        echo "   4. Open Help Center"
        echo "   5. Advanced setup and configuration"
        echo
        echo "   r. Continue to main menu"
        echo "   q. Quit"
        echo
        ask choice "Select:"
        case "$choice" in
            1) guided_deployment_menu; return ;;
            2) title "Requirements"; fortifylab_welcome_warnings; printf '\n'; fortifylab_welcome_locations; printf '\n'; fortifylab_welcome_snapshot; press_any ;;
            3) guided_profile_menu ;;
            4) help_center ;;
            5) advanced_menu ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid choice"; sleep 1 ;;
        esac
    done
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
        echo "   1. Guided deployment (recommended)"
        echo "   2. Express deployment"
        echo "   3. Resume or repair deployment"
        echo "   4. Manage individual components (expert)"
        echo "   5. Sample applications"
        echo "   6. Kubernetes Dashboard access"

        section "Diagnostics and advanced"
        echo "   7. Diagnostics / live status"
        echo "   8. Advanced setup and configuration"

        section "Operations"
        echo "   9. Lab lifecycle controls"
        echo "  10. Stream logs (all pods)"
        echo "  11. Cluster snapshot"
        echo "  12. Tail one pod"
        echo "  13. URLs & credentials"
        echo "  14. Tools and FCLI readiness"
        echo "  15. Image versions"
        echo "  16. Configuration editor"

        section "Learn"
        echo "  17. Help Center / Fortify Knowledge Center"
        echo "  18. Operational guidance and troubleshooting"
        echo "  19. View wizard log"

        echo
        echo "   q. Quit"
        echo
        ask choice "Select:"

        case "$choice" in
            1)  guided_deployment_menu ;;
            2)  deploy_from_scratch ;;
            3)  resume_repair ;;
            4)  apps_menu ;;
            5)  sample_apps_menu ;;
            6)  dashboard_access_menu ;;
            7)  live_status ;;
            8)  advanced_menu ;;
            9)  lab_lifecycle_menu ;;
           10)  stream_logs ;;
           11)  cluster_status ;;
           12)  logs_menu ;;
           13)  urls_creds ;;
           14)  fcli_tools_menu ;;
           15)  versions_menu ;;
           16)  edit_env ;;
           17)  help_center ;;
           18)  operational_guidance_menu ;;
           19)  wizard_log_viewer ;;
            [Qq]) clear; exit 0 ;;
            *)   error "Invalid choice"; sleep 1 ;;
        esac
    done
}
