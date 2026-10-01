#!/usr/bin/env bash
# shellcheck shell=bash
# Module: operations/advanced-menus
# Responsibility: Render advanced, troubleshooting, and operational-guidance menus.
# Requires: title, ask, error, note, press_any; prereqs_menu, license_menu,
#           certs_secrets_menu, configure_menu, edit_env, cluster_profile_menu,
#           setup_menu; operational/help/runbook functions from runbooks.sh.
# Exports: advanced_menu, operational_troubleshooting_menu, operational_guidance_menu.
# Side effects: Dispatches selected operations.
# Interactive: yes.

if [[ -n "${FORTIFYLAB_WIZARD_ADVANCED_MENUS_LOADED:-}" ]]; then
    return 0
fi
FORTIFYLAB_WIZARD_ADVANCED_MENUS_LOADED=1

advanced_menu() {
    while true; do
        title "Advanced setup and configuration"
        cat <<EOF

  1. Install prerequisites
  2. License files
  3. Generate certificates and Secrets
  4. Configure DNS, SSC token, LIM, and Dashboard access
  5. Configuration editor (.env, domain, root CA)
  6. Cluster profiles and remote readiness
  7. Setup readiness summary

  r. Return
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1) prereqs_menu ;;
            2) license_menu ;;
            3) certs_secrets_menu ;;
            4) configure_menu ;;
            5) edit_env ;;
            6) cluster_profile_menu ;;
            7) setup_menu ;;
            [Rr]) return ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

operational_troubleshooting_menu() {
    local choice topic help_topic
    while true; do
        title "Troubleshooting assistant"
        cat <<'EOF'

  1. Deployment step failed       7. SSC
  2. Pod is Pending               8. ScanCentral SAST
  3. Pod is restarting            9. ScanCentral DAST
  4. URL does not open           10. Kubernetes Dashboard
  5. TLS warning                 11. License
  6. Database                    12. Container registry

  r. Return
EOF
        ask choice "Select a symptom:"
        case "$choice" in
            1) topic=failed-deploy ;; 2) topic=pending-pods ;;
            3) topic=restarting-pods ;; 4) topic=url ;; 5) topic=tls ;;
            6) topic=database ;; 7) topic=ssc ;; 8) topic=sast ;;
            9) topic=dast ;; 10) topic=dashboard ;; 11) topic=license ;;
            12) topic=registry ;; [Rr]) return ;;
            *) error "Invalid selection"; sleep 1; continue ;;
        esac
        echo
        operational_troubleshooting_topic "$topic"
        echo
        help_topic=$(help_failure_topic "$topic") || {
            error "No documentation mapping exists for troubleshooting topic: $topic"
            press_any
            continue
        }
        help_print_topic_reference "$help_topic"
        press_any
    done
}

operational_guidance_menu() {
    local choice output_dir bundle
    while true; do
        title "Operational guidance"
        cat <<'EOF'

  1. Environment overview
  2. Deployment plan
  3. Unfinished-work summary
  4. Troubleshooting assistant
  5. Networking, URLs, and TLS
  6. Secrets and license safety
  7. Lifecycle and data safety
  8. Versions and compatibility
  9. Backup and recovery guidance
 10. First-scan walkthrough
 11. Create sanitized diagnostics bundle

  r. Return
EOF
        ask choice "Select:"
        case "$choice" in
            1) wizard_environment_overview; press_any ;;
            2) wizard_deployment_plan; press_any ;;
            3) operational_unfinished_summary; press_any ;;
            4) operational_troubleshooting_menu ;;
            5) operational_print_urls; echo; operational_render_guide networking; press_any ;;
            6) operational_secret_help; echo; operational_render_guide secrets; press_any ;;
            7) operational_lifecycle_help; echo; operational_render_guide deployment; press_any ;;
            8) operational_version_overview; echo; operational_render_guide versions; press_any ;;
            9) operational_render_guide recovery; press_any ;;
            10) operational_render_guide first-scan; press_any ;;
            11)
                output_dir="${XDG_STATE_HOME:-$HOME/.local/state}/fortify-lab/diagnostics"
                if ! mkdir -p -- "$output_dir" || ! chmod 700 -- "$output_dir"; then
                    error "Could not create the private diagnostics output directory."
                    press_any
                    continue
                fi
                if bundle=$(operational_create_diagnostics_bundle "$output_dir"); then
                    note "Sanitized bundle created: $bundle"
                    note "Review it before sharing; no automated sanitizer can prove all context is safe."
                else
                    error "Diagnostics bundle creation failed."
                fi
                press_any
                ;;
            [Rr]) return ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

