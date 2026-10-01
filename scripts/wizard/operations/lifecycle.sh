# shellcheck shell=bash
# Module: operations/lifecycle
# Responsibility: Coordinated lab lifecycle selection, start, stop, teardown, destroy, and menu flow.
# Requires: application registry, guided deployment helpers, UI helpers, app-runtime
# Exports: lab_lifecycle_*
# Side effects: Starts, stops, or destroys selected Kubernetes workloads after authorization.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_LIFECYCLE_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_LIFECYCLE_LOADED=1

lab_lifecycle_current_profile() {
    guided_apply_deployment_profile "${GUIDED_DEPLOYMENT_PROFILE:-${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}}"
}

lab_lifecycle_step_is_workload() {
    case "$1" in
        mysql|postgresql|ssc|lim|sast_controller|sast_sensor|dast_core|dast_scanner|sample_juice_shop|sample_webgoat|sample_dvwa) return 0 ;;
        *) return 1 ;;
    esac
}

lab_lifecycle_app_index_selected() {
    local idx="$1" step="${APP_GUIDED_STEP[$idx]:-}"
    case "$step" in
        mysql|postgresql|ssc|lim) guided_component_selected "$step" ;;
        sast) guided_component_selected sast_controller || guided_component_selected sast_sensor ;;
        dast) guided_component_selected dast_core || guided_component_selected dast_scanner ;;
        sample_juice_shop|sample_webgoat|sample_dvwa) guided_component_selected "$step" ;;
        *) return 1 ;;
    esac
}

lab_lifecycle_selected_pod_prefixes() {
    local idx prefix prefixes=""
    lab_lifecycle_current_profile >/dev/null 2>&1 || true
    for idx in "${!APP_PODS[@]}"; do
        lab_lifecycle_app_index_selected "$idx" || continue
        prefix="${APP_PODS[$idx]}"
        case " $prefixes " in
            *" $prefix "*) ;;
            *) prefixes="${prefixes:+$prefixes }$prefix" ;;
        esac
    done
    printf '%s\n' "$prefixes"
}

lab_lifecycle_selected_step_indexes() {
    local idx id
    lab_lifecycle_current_profile >/dev/null 2>&1 || true
    for idx in "${!GUIDED_STEP_ID[@]}"; do
        id="${GUIDED_STEP_ID[$idx]}"
        lab_lifecycle_step_is_workload "$id" && printf '%s\n' "$idx"
    done
}

lab_lifecycle_step_stop_destroy_script() {
    local operation="$1" step="$2"
    case "$operation:$step" in
        stop:mysql) printf '%s\n' "apps/mysql/stop.sh" ;;
        stop:postgresql) printf '%s\n' "apps/postgresql/stop.sh" ;;
        stop:ssc) printf '%s\n' "apps/ssc/stop.sh" ;;
        stop:lim) printf '%s\n' "apps/lim/stop.sh" ;;
        stop:sast_controller|stop:sast_sensor) printf '%s\n' "apps/scsast/stop.sh" ;;
        stop:dast_core) printf '%s\n' "apps/scdast/core/stop.sh" ;;
        stop:dast_scanner) printf '%s\n' "apps/scdast/scanner/stop.sh" ;;
        destroy:mysql) printf '%s\n' "apps/mysql/destroy.sh" ;;
        destroy:postgresql) printf '%s\n' "apps/postgresql/destroy.sh" ;;
        destroy:ssc) printf '%s\n' "apps/ssc/destroy.sh" ;;
        destroy:lim) printf '%s\n' "apps/lim/destroy.sh" ;;
        destroy:sast_controller|destroy:sast_sensor) printf '%s\n' "apps/scsast/destroy.sh" ;;
        destroy:dast_core) printf '%s\n' "apps/scdast/core/destroy.sh" ;;
        destroy:dast_scanner) printf '%s\n' "apps/scdast/scanner/destroy.sh" ;;
        *) return 1 ;;
    esac
}

lab_lifecycle_script_list() {
    local operation="$1" scope="${2:-selected}" idx field script seen="" step
    if [ "$scope" = "all" ]; then
        for ((idx=${#APP_LABEL[@]} - 1; idx >= 0; idx--)); do
            app_index_in_full_lifecycle "$idx" || continue
            case "$operation" in
                destroy) field="${APP_DESTROY[$idx]}" ;;
                stop) field="${APP_STOP[$idx]}" ;;
                *) return 1 ;;
            esac
            for script in $field; do
                printf '  - %-20s %s\n' "${APP_LABEL[$idx]}" "$script"
            done
        done
        return 0
    fi
    mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
    for ((idx=${#_lab_lifecycle_indexes[@]} - 1; idx >= 0; idx--)); do
        step="${GUIDED_STEP_ID[${_lab_lifecycle_indexes[$idx]}]}"
        script=$(lab_lifecycle_step_stop_destroy_script "$operation" "$step") || continue
        case " $seen " in
            *" $script "*) continue ;;
        esac
        seen="${seen:+$seen }$script"
        printf '  - %-20s %s\n' "${GUIDED_STEP_LABEL[${_lab_lifecycle_indexes[$idx]}]}" "$script"
    done
}

lab_shutdown_deployments() {
    local scope="${1:-selected}" idx rc=0 script step seen=""
    section "Shutdown lab deployments"
    if [ "$scope" = "all" ]; then
        note "Stopping all lab workloads in dependency-safe order. Persistent data is preserved."
        wizard_log_event "action=lab_lifecycle_start operation=shutdown scope=all mode=non_destructive"
        for ((idx=${#APP_LABEL[@]} - 1; idx >= 0; idx--)); do
            app_index_in_full_lifecycle "$idx" || continue
            note "Stopping ${APP_LABEL[$idx]}..."
            wizard_log_event "action=lab_lifecycle_component operation=shutdown scope=all component=${APP_GUIDED_STEP[$idx]}"
            run_app_scripts "${APP_STOP[$idx]}"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=shutdown scope=all state=failed component=${APP_GUIDED_STEP[$idx]} exit_code=$rc"
                return "$rc"
            fi
        done
    else
        lab_lifecycle_current_profile
        note "Stopping selected profile workloads: $GUIDED_DEPLOYMENT_PROFILE_LABEL. Persistent data is preserved."
        wizard_log_event "action=lab_lifecycle_start operation=shutdown scope=selected profile=$GUIDED_DEPLOYMENT_PROFILE mode=non_destructive"
        mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
        for ((idx=${#_lab_lifecycle_indexes[@]} - 1; idx >= 0; idx--)); do
            step="${GUIDED_STEP_ID[${_lab_lifecycle_indexes[$idx]}]}"
            script=$(lab_lifecycle_step_stop_destroy_script stop "$step") || continue
            case " $seen " in
                *" $script "*) continue ;;
            esac
            seen="${seen:+$seen }$script"
            note "Stopping ${GUIDED_STEP_LABEL[${_lab_lifecycle_indexes[$idx]}]}..."
            wizard_log_event "action=lab_lifecycle_component operation=shutdown scope=selected component=$step"
            run_app_scripts "$script"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=shutdown scope=selected state=failed component=$step exit_code=$rc"
                return "$rc"
            fi
        done
    fi
    wizard_log_event "action=lab_lifecycle_finish operation=shutdown scope=$scope state=complete"
    note "Lab workloads stopped. Data volumes and configuration remain in place."
}

lab_start_deployments() {
    local scope="${1:-selected}" idx rc=0 previous_mode="${GUIDED_MODE_CONTEXT:-}" step label
    section "Start lab deployments"
    if [ "$scope" = "all" ]; then
        note "Starting all lab workloads in dependency order and verifying readiness after each component."
        wizard_log_event "action=lab_lifecycle_start operation=start scope=all mode=non_destructive"
        GUIDED_MODE_CONTEXT=lifecycle
        local -a _lifecycle_ids=()
        for idx in "${!APP_LABEL[@]}"; do
            app_index_in_full_lifecycle "$idx" || continue
            _lifecycle_ids+=("${APP_GUIDED_STEP[$idx]}")
        done
        guided_board_reset "${_lifecycle_ids[@]}"
        for idx in "${!APP_LABEL[@]}"; do
            app_index_in_full_lifecycle "$idx" || continue
            guided_run_and_verify "${APP_GUIDED_STEP[$idx]}" "${APP_LABEL[$idx]}"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                GUIDED_MODE_CONTEXT="$previous_mode"
                wizard_log_event "action=lab_lifecycle_finish operation=start scope=all state=failed component=${APP_GUIDED_STEP[$idx]} exit_code=$rc"
                return "$rc"
            fi
        done
    else
        lab_lifecycle_current_profile
        note "Starting selected profile workloads: $GUIDED_DEPLOYMENT_PROFILE_LABEL."
        wizard_log_event "action=lab_lifecycle_start operation=start scope=selected profile=$GUIDED_DEPLOYMENT_PROFILE mode=non_destructive"
        GUIDED_MODE_CONTEXT=lifecycle
        mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
        local -a _lifecycle_ids=()
        for idx in "${_lab_lifecycle_indexes[@]}"; do
            _lifecycle_ids+=("${GUIDED_STEP_ID[$idx]}")
        done
        guided_board_reset "${_lifecycle_ids[@]}"
        for idx in "${_lab_lifecycle_indexes[@]}"; do
            step="${GUIDED_STEP_ID[$idx]}"
            label="${GUIDED_STEP_LABEL[$idx]}"
            guided_run_and_verify "$step" "$label"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                GUIDED_MODE_CONTEXT="$previous_mode"
                wizard_log_event "action=lab_lifecycle_finish operation=start scope=selected state=failed component=$step exit_code=$rc"
                return "$rc"
            fi
        done
    fi
    GUIDED_MODE_CONTEXT="$previous_mode"
    wizard_log_event "action=lab_lifecycle_finish operation=start scope=$scope state=complete"
    note "Lab workloads are started and verified."
}

lab_teardown_preview() {
    local scope="${1:-selected}"
    if [ "$scope" = "all" ]; then
        section "Full lab teardown preview"
        cat <<EOF
This destructive operation runs every component destroy script below in
dependency-safe order. It deletes application deployments and their data so
the lab can be started again from a clean slate.

EOF
    else
        lab_lifecycle_current_profile
        section "Selected profile teardown preview"
        cat <<EOF
This destructive operation runs destroy scripts only for the selected profile:
$GUIDED_DEPLOYMENT_PROFILE_LABEL. Dependencies are included only when the
profile requires them, and unrelated lab workloads are left alone.

EOF
    fi
    lab_lifecycle_script_list destroy "$scope"
}

lab_destroy_deployments() {
    local scope="${1:-selected}" idx rc=0 confirmation expected script step seen=""
    if [ "$scope" = "all" ]; then
        expected="DESTROY FORTIFY LAB"
    else
        expected="DESTROY SELECTED PROFILE"
    fi
    fortify_lab_show_action_warning destructive
    lab_teardown_preview "$scope"
    printf '\nType %s to continue: ' "$expected"
    IFS= read -r confirmation
    if [ "$confirmation" != "$expected" ]; then
        note "Teardown cancelled."
        wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=$scope state=cancelled"
        return 1
    fi
    wizard_log_event "action=lab_lifecycle_start operation=destroy scope=$scope mode=destructive"
    if [ "$scope" = "all" ]; then
        for ((idx=${#APP_LABEL[@]} - 1; idx >= 0; idx--)); do
            app_index_in_full_lifecycle "$idx" || continue
            note "Destroying ${APP_LABEL[$idx]}..."
            wizard_log_event "action=lab_lifecycle_component operation=destroy scope=all component=${APP_GUIDED_STEP[$idx]}"
            run_app_scripts "${APP_DESTROY[$idx]}"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=all state=failed component=${APP_GUIDED_STEP[$idx]} exit_code=$rc"
                return "$rc"
            fi
        done
    else
        mapfile -t _lab_lifecycle_indexes < <(lab_lifecycle_selected_step_indexes)
        for ((idx=${#_lab_lifecycle_indexes[@]} - 1; idx >= 0; idx--)); do
            step="${GUIDED_STEP_ID[${_lab_lifecycle_indexes[$idx]}]}"
            script=$(lab_lifecycle_step_stop_destroy_script destroy "$step") || continue
            case " $seen " in
                *" $script "*) continue ;;
            esac
            seen="${seen:+$seen }$script"
            note "Destroying ${GUIDED_STEP_LABEL[${_lab_lifecycle_indexes[$idx]}]}..."
            wizard_log_event "action=lab_lifecycle_component operation=destroy scope=selected component=$step"
            run_app_scripts "$script"
            rc=$?
            if [ "$rc" -ne 0 ]; then
                wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=selected state=failed component=$step exit_code=$rc"
                return "$rc"
            fi
        done
    fi
    wizard_log_event "action=lab_lifecycle_finish operation=destroy scope=$scope state=complete"
    note "Lab deployments and data have been destroyed for the requested scope."
}

lab_lifecycle_menu() {
    local choice
    while true; do
        lab_lifecycle_current_profile
        title "Lab lifecycle controls"
        cat <<EOF

  Active profile: $GUIDED_DEPLOYMENT_PROFILE_LABEL

  1. Shutdown selected profile workloads (preserve data)
  2. Start selected profile workloads
  3. Destroy selected profile deployments and data

  4. Shutdown all lab deployments (preserve data)
  5. Start all lab deployments
  6. Destroy all lab deployments and data
  7. Complete lab reset wizard

  r. Return
  q. Quit
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1)
                confirm "Stop selected profile workloads while preserving data?" || continue
                lab_shutdown_deployments selected
                press_any ;;
            2)
                lab_start_deployments selected
                press_any ;;
            3)
                lab_destroy_deployments selected
                press_any ;;
            4)
                confirm "Stop all lab workloads while preserving data?" || continue
                lab_shutdown_deployments all
                press_any ;;
            5)
                lab_start_deployments all
                press_any ;;
            6)
                lab_destroy_deployments all
                press_any ;;
            7)
                lab_reset_menu ;;
            [Rr]) return ;;
            [Qq]) clear; exit 0 ;;
            *) error "Invalid"; sleep 1 ;;
        esac
    done
}


# ============================================================
