# shellcheck shell=bash
# Module: operations/apps-menu
# Responsibility: Application menus, component actions, worker scaling, and credential display dispatch.
# Requires: application registry, app-runtime, UI helpers, kubectl
# Exports: apps_menu, sample_apps_menu, apps_menu_for_scope, app_action_menu, scale_workers, show_app_creds
# Side effects: Dispatches lifecycle, scaling, log, and credential actions selected by the operator.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_APPS_MENU_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_APPS_MENU_LOADED=1

# Apps submenu
# ============================================================

apps_menu() {
    apps_menu_for_scope "all"
}

sample_apps_menu() {
    fortify_lab_show_action_warning vulnerable-sample
    apps_menu_for_scope "samples"
}

apps_menu_for_scope() {
    local scope="${1:-all}" heading="Apps"
    [ "$scope" = "samples" ] && heading="Sample applications"
    while true; do
        title "$heading"
        if [ "$scope" = "samples" ]; then
            printf '\n  Intentionally vulnerable lab targets for SAST and DAST practice.\n'
            printf '  Keep these applications isolated to your lab network.\n'
        fi
        printf '\n  %-3s %-20s %s\n' "#" "Name" "Status"
        printf '  %s\n' "─────────────────────────────────────"
        local i display_idx visible=0 visible_indices=()
        for i in "${!APP_LABEL[@]}"; do
            if [ "$scope" = "samples" ]; then
                app_index_is_sample "$i" || continue
            fi
            visible=$((visible + 1))
            display_idx="$visible"
            [ "$scope" = "all" ] && display_idx=$((i + 1))
            visible_indices[$visible]="$i"
            printf '  %-3d %-20s %s\n' \
                "$display_idx" "${APP_LABEL[$i]}" "$(app_status "${APP_PODS[$i]}")"
        done
        [ "$visible" -eq 0 ] && printf '  %s\n' "No sample applications are registered."
        echo
        echo "  r. Return to main menu"
        echo "  q. Quit"
        echo
        ask choice "Select an app:"

        case "$choice" in
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            ''|*[!0-9]*) error "Invalid selection"; sleep 1 ;;
            *)
                if [ "$choice" -ge 1 ]; then
                    if [ "$scope" = "samples" ]; then
                        if [ "$choice" -le "$visible" ] && [ -n "${visible_indices[$choice]:-}" ]; then
                            app_action_menu "${visible_indices[$choice]}"
                        else
                            error "Select one of the sample application numbers shown above."
                            sleep 1
                        fi
                    elif [ "$choice" -le "${#APP_LABEL[@]}" ]; then
                        app_action_menu $((choice - 1))
                    else
                        error "Out of range"
                        sleep 1
                    fi
                else
                    error "Out of range"
                    sleep 1
                fi
                ;;
        esac
    done
}

app_action_menu() {
    local idx="$1"
    while true; do
        title "${APP_LABEL[$idx]}"
        local url=""
        url=$(app_url_display_for_index "$idx")

        echo
        printf '  Status: %s\n' "$(app_status "${APP_PODS[$idx]}")"
        [ -n "$url" ] && printf '  URL:    %s\n' "$url"
        echo

        echo "  1. Start / Upgrade"
        echo "  2. Stop"
        echo "  3. Destroy (deletes data)"
        echo "  4. Logs"
        echo "  5. Show URL & credentials"
        case "${APP_LABEL[$idx]}" in
            "ScanCentral SAST"|"ScanCentral DAST")
                echo "  6. Scale workers"
                ;;
        esac
        echo
        echo "  r. Return"
        echo "  q. Quit"
        echo
        ask choice "Select:"

        case "$choice" in
            1)
                if app_start_config_guard "$idx"; then
                    run_app_scripts "${APP_START[$idx]}"
                fi
                press_any ;;
            2)
                run_app_scripts "${APP_STOP[$idx]}"
                press_any ;;
            3)
                fortify_lab_show_action_warning destructive
                if confirm "DELETE ${APP_LABEL[$idx]} and its data. Continue?"; then
                    run_app_scripts "${APP_DESTROY[$idx]}"
                fi
                press_any ;;
            4) logs_for_prefix "${APP_PODS[$idx]}" ;;
            5) show_app_creds "$idx"; press_any ;;
            6) scale_workers "$idx"; press_any ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}

scale_workers() {
    local idx="$1" sts replicas
    case "${APP_LABEL[$idx]}" in
        "ScanCentral SAST") sts="scancentral-sast-worker-linux" ;;
        "ScanCentral DAST") sts="sdast-scanner-scancentral-dast-scanner" ;;
        *) error "Scaling not supported for ${APP_LABEL[$idx]}"; return ;;
    esac
    local current
    current=$($KUBECTL -n "$NAMESPACE" get statefulset "$sts" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
    note "Current $sts replicas: $current"
    ask replicas "New replica count (or empty to cancel):"
    [ -z "$replicas" ] && return
    [[ "$replicas" =~ ^[0-9]+$ ]] || { error "Not a number"; return; }
    $KUBECTL -n "$NAMESPACE" scale statefulset "$sts" --replicas="$replicas"
}

show_app_creds() {
    local idx="$1" url=""
    url=$(app_url_display_for_index "$idx")
    section "${APP_LABEL[$idx]}"
    [ -n "$url" ] && printf '  URL: %s\n' "$url"
    case "${APP_LABEL[$idx]}" in
        SSC)
            echo "  Login username: admin"
            echo "  Password: refer to the SSC documentation for the default password."
            ;;
        LIM)
            echo "  Login username: lim_admin"
            echo "  Password: stored in Kubernetes Secret lim-admin-credentials"
            ;;
        "ScanCentral SAST")
            echo "  Controller URL: $url"
            echo "  Tokens: use URLs & credentials to reveal or retrieve commands."
            ;;
        "ScanCentral DAST")
            echo "  API URL: ${SCDAST_API_URL:-<unset>}"
            echo "  Credentials: use URLs & credentials to reveal or retrieve commands."
            ;;
    esac
}


# ============================================================
