# shellcheck shell=bash
# Module: flight-plans/staging
# Responsibility: Component mapping, drift analysis, staged updates, and upgrade safety flows.
# Layer: operation/orchestration
# Requires: flight-plans/catalog, environment-store/editor helpers, UI helpers, ENV_FILE.
# Exports: component, drift, staging, impact, selection, and upgrade functions.
# Side effects: Stages and may apply environment configuration changes after confirmation.
# Interactive: some orchestration functions prompt.
[ -n "${FORTIFY_WIZARD_FLIGHT_PLAN_STAGING_LOADED:-}" ] && return 0
FORTIFY_WIZARD_FLIGHT_PLAN_STAGING_LOADED=1

flight_plan_component_keys() {
    case "$1" in
        ssc) printf '%s\n' FORTIFY_SSC_CHART_VERSION FORTIFY_SSC_IMAGE_TAG ;;
        lim) printf '%s\n' FORTIFY_LIM_CHART_VERSION ;;
        sast) printf '%s\n' FORTIFY_SCSAST_CHART_VERSION FORTIFY_SCSAST_CTRL_IMAGE_TAG FORTIFY_SCSAST_WORKER_IMAGE_TAG ;;
        dast) printf '%s\n' FORTIFY_SCDAST_CHART_VERSION ;;
        *) return 1 ;;
    esac
}

flight_plan_component_label() {
    case "$1" in
        ssc) printf '%s\n' "Software Security Center" ;;
        lim) printf '%s\n' "License and Infrastructure Manager" ;;
        sast) printf '%s\n' "ScanCentral SAST" ;;
        dast) printf '%s\n' "ScanCentral DAST" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

flight_plan_component_step() {
    case "$1" in
        ssc) printf '%s\n' ssc ;;
        lim) printf '%s\n' lim ;;
        sast) printf '%s\n' sast ;;
        dast) printf '%s\n' dast ;;
        *) return 1 ;;
    esac
}

flight_plan_value_for_key() {
    local plan_id="$1" key="$2" line
    while IFS= read -r line; do
        [ "${line%%=*}" = "$key" ] || continue
        printf '%s\n' "${line#*=}"
        return 0
    done < <(flight_plan_tool env-updates "$plan_id")
    return 1
}

flight_plan_stage_component_from_plan() {
    local array_name="$1" component="$2" plan_id="$3" key value changed=0
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        value=$(flight_plan_value_for_key "$plan_id" "$key" 2>/dev/null || true)
        [ -n "$value" ] || continue
        env_pending_set "$array_name" "$key" "$value"
        changed=1
    done < <(flight_plan_component_keys "$component")
    return $((changed == 0))
}

flight_plan_restore_component_baseline() {
    local array_name="$1" component="$2" plan_id="${3:-$(flight_plan_selected_id)}"
    flight_plan_stage_component_from_plan "$array_name" "$component" "$plan_id"
}

flight_plan_component_drift_status() {
    local component="$1" plan_id="${2:-$(flight_plan_selected_id)}" key expected current drift=0 total=0
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        expected=$(flight_plan_value_for_key "$plan_id" "$key" 2>/dev/null || true)
        current=$(env_current_value "$key")
        [ -n "$expected" ] || continue
        total=$((total + 1))
        [ "$current" = "$expected" ] || drift=$((drift + 1))
    done < <(flight_plan_component_keys "$component")
    if [ "$total" -eq 0 ]; then
        printf 'unknown\n'
    elif [ "$drift" -eq 0 ]; then
        printf 'aligned\n'
    else
        printf 'custom override (%d/%d drifted)\n' "$drift" "$total"
    fi
}

flight_plan_pending_drift_components() {
    local fallback pair key="FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS"
    fallback="$(env_current_value "$key")"
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] || continue
        printf '%s\n' "${pair#*=}"
        return 0
    done
    printf '%s\n' "$fallback"
}

flight_plan_stage_drift_marker() {
    local array_name="$1" component="$2" current item next=""
    local -n pending_ref="$array_name"
    current="$(flight_plan_pending_drift_components "${pending_ref[@]}")"
    IFS=',' read -r -a _flight_plan_drift_items <<<"$current"
    for item in "${_flight_plan_drift_items[@]}"; do
        [ -n "$item" ] || continue
        [ "$item" = "$component" ] && continue
        next="${next:+$next,}$item"
    done
    next="${next:+$next,}$component"
    env_pending_set "$array_name" FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS "$next"
}

flight_plan_clear_drift_marker() {
    local array_name="$1" component="$2" current item next=""
    local -n pending_ref="$array_name"
    current="$(flight_plan_pending_drift_components "${pending_ref[@]}")"
    IFS=',' read -r -a _flight_plan_drift_items <<<"$current"
    for item in "${_flight_plan_drift_items[@]}"; do
        [ -n "$item" ] || continue
        [ "$item" = "$component" ] && continue
        next="${next:+$next,}$item"
    done
    env_pending_set "$array_name" FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS "$next"
}

flight_plan_print_component_impact() {
    local component="$1" target_plan="$2" key current target
    printf '  Component: %s\n' "$(flight_plan_component_label "$component")"
    printf '  Baseline Flight Plan: %s\n' "$(flight_plan_selected_id)"
    printf '  Target source: %s\n' "$target_plan"
    printf '  Current drift: %s\n' "$(flight_plan_component_drift_status "$component")"
    printf '\n  %-36s %-22s %s\n' "Key" "Current" "Target"
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        current=$(env_current_value "$key")
        target=$(flight_plan_value_for_key "$target_plan" "$key" 2>/dev/null || true)
        printf '  %-36s %-22s %s\n' "$key" "${current:-<unset>}" "${target:-<review required>}"
    done < <(flight_plan_component_keys "$component")
}

flight_plan_print_upgrade_impact() {
    local target_plan="$1" current_plan current_family target_family relation="upgrade/change" output rc=0 drift=0 unknown=0
    current_plan="$(flight_plan_selected_id)"
    current_family=$(flight_plan_tool show "$current_plan" 2>/dev/null | awk -F: '/^Family:/ { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit }')
    target_family=$(flight_plan_tool show "$target_plan" 2>/dev/null | awk -F: '/^Family:/ { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit }')
    if [ -n "$current_family" ] && [ -n "$target_family" ]; then
        if [ "$target_family" = "$current_family" ]; then
            relation="same release family"
        elif printf '%s\n%s\n' "$target_family" "$current_family" | sort -V | tail -1 | grep -qx "$target_family"; then
            relation="upgrade"
        else
            relation="downgrade or rollback"
        fi
    fi
    output=$(flight_plan_tool compare-env "$target_plan" --env-file "$ENV_FILE" 2>/dev/null) || rc=$?
    drift=$(printf '%s\n' "$output" | awk -F'\t' '$2=="drifted" {c++} END{print c+0}')
    unknown=$(printf '%s\n' "$output" | awk -F'\t' '$2=="unknown" {c++} END{print c+0}')
    printf '  Current Flight Plan: %s\n' "$current_plan"
    printf '  Target Flight Plan:  %s\n' "$target_plan"
    printf '  Change type:         %s\n' "$relation"
    printf '  Target differences:  %d drifted, %d unknown\n' "$drift" "$unknown"
    printf '  Database versions:   managed separately; not changed by Flight Plan upgrades\n'
    printf '\nTarget release overlays:\n'
    FORTIFY_FLIGHT_PLAN="$target_plan" release_overlay_report
    [ "$rc" -eq 0 ] || true
}

flight_plan_upgrade_safety_note() {
    cat <<'EOF'

Upgrade safety
  Take a VM/LXC snapshot or backup before upgrading a lab with data you care
  about. Restoring .env is configuration rollback only; it does not reverse SSC,
  LIM, SAST, DAST, database schema migrations, PVC contents, or Helm history.
  Downgrades after an application has migrated data should be treated as data
  recovery or full lab reset work.
EOF
}

flight_plan_component_override_safety_note() {
    cat <<'EOF'

Component override safety
  This creates a custom/drifted lab. Do not describe the environment as the
  selected Flight Plan when only one component has been changed. Restore the
  component to the Flight Plan baseline when compatibility testing is complete.
EOF
}

flight_plan_stage_updates() {
    local array_name="$1" plan_id="$2" line count=0
    local -n pending_ref="$array_name"
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        env_pending_set "$array_name" "${line%%=*}" "${line#*=}"
        count=$((count + 1))
    done < <(flight_plan_tool env-updates "$plan_id")
    if [ "$count" -eq 0 ]; then
        error "Flight Plan $plan_id has no populated component versions yet. Nothing was staged."
        return 1
    fi
    env_pending_set "$array_name" FORTIFY_FLIGHT_PLAN "$plan_id"
}


flight_plan_choose_menu() {
    local result_var="$1" include_candidates="${2:-}" records=() choice selected_plan_id label status family idx
    mapfile -t records < <(flight_plan_list_records "$include_candidates")
    [ "${#records[@]}" -gt 0 ] || { error "No usable Flight Plans found. Validate config/flight-plans.toml."; press_any; return 1; }
    while true; do
        title "Select Fortify Flight Plan"
        printf '\nCurrent: %s\n\n' "$(flight_plan_selected_id)"
        section "Available Flight Plans"
        for idx in "${!records[@]}"; do
            IFS=$'\t' read -r selected_plan_id label status family <<<"${records[$idx]}"
            printf '  %2d. %-18s %-13s %s\n' "$((idx + 1))" "$label" "$(flight_plan_status_label "$status")" "family $family"
        done
        cat <<'EOF'

  b. Back
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            [Bb]|"") return 0 ;;
            ''|*[!0-9]*) error "Select a Flight Plan number shown above."; sleep 1 ;;
            *)
                if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#records[@]}" ]; then
                    error "Out of range"; sleep 1; continue
                fi
                IFS=$'\t' read -r selected_plan_id label status family <<<"${records[$((choice - 1))]}"
                printf -v "$result_var" '%s' "$selected_plan_id"
                FLIGHT_PLAN_CHOICE_LABEL="$label"
                return 0
                ;;
        esac
    done
}

flight_plan_preview_menu() {
    local include_candidates="${1:-}" plan_id
    flight_plan_choose_menu plan_id "$include_candidates" || return $?
    [ -n "$plan_id" ] || return 0
    section "Flight Plan details"
    flight_plan_tool show "$plan_id"
    press_any
}

flight_plan_select_menu() {
    local array_name="$1" include_candidates="${2:-}" plan_id
    FLIGHT_PLAN_CHOICE_LABEL=""
    flight_plan_choose_menu plan_id "$include_candidates" || return $?
    [ -n "$plan_id" ] || return 0
    if flight_plan_stage_updates "$array_name" "$plan_id"; then
        note "Flight Plan staged: ${FLIGHT_PLAN_CHOICE_LABEL:-$(flight_plan_label_for_id "$plan_id")}"
        flight_plan_upgrade_safety_note
    fi
    press_any
}

flight_plan_full_upgrade_flow() {
    local array_name="$1" target_plan="${2:-}"
    [ -n "$target_plan" ] || flight_plan_choose_menu target_plan all || return $?
    [ -n "$target_plan" ] || return 0
    if [ -z "$(flight_plan_tool env-updates "$target_plan" 2>/dev/null)" ]; then
        error "Flight Plan $target_plan has no populated component versions yet. Nothing to stage."
        press_any
        return 0
    fi
    section "Flight Plan upgrade impact"
    flight_plan_print_upgrade_impact "$target_plan"
    flight_plan_upgrade_safety_note
    if confirm "Stage full Flight Plan upgrade to $target_plan?"; then
        flight_plan_stage_updates "$array_name" "$target_plan"
        section "Pending .env changes"
        local -n pending_ref="$array_name"
        env_preview_changes "${pending_ref[@]}"
        note "Full Flight Plan upgrade staged. Use Apply pending version changes to write .env with a backup."
    else
        note "Flight Plan upgrade was not staged."
    fi
}

flight_plan_upgrade_menu() {
    flight_plan_full_upgrade_flow "$@"
}

# Non-interactive entry point for `./start_wizard.sh apply-flight-plan <id> [--yes]`
# -- stages a Flight Plan's component versions into .env with a backup, reusing
# the same staging/preview/apply machinery as the interactive wizard menu, but
# never prompts and never blocks on stdin. Without --yes this is a dry run,
# matching the promote/promote-local CLI convention.
wizard_apply_flight_plan() {
    local plan_id="$1" auto_yes="${2:-0}" pending=() line count=0
    wizard_doctor_load_env
    if [ ! -s "$ENV_FILE" ]; then
        error ".env does not exist yet. Create one (cp .env.example .env) before applying a Flight Plan."
        return 1
    fi
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        pending+=("$line")
        count=$((count + 1))
    done < <(flight_plan_tool env-updates "$plan_id")
    if [ "$count" -eq 0 ]; then
        error "Flight Plan $plan_id has no populated component versions yet. Nothing to apply."
        return 1
    fi
    pending+=("FORTIFY_FLIGHT_PLAN=$plan_id")
    section "Flight Plan upgrade impact"
    flight_plan_print_upgrade_impact "$plan_id"
    flight_plan_upgrade_safety_note
    section "Pending .env changes"
    env_preview_changes "${pending[@]}"
    if [ "$auto_yes" -ne 1 ]; then
        echo
        note "Dry run only. Re-run with --yes to write .env (a backup is created first)."
        return 0
    fi
    env_apply_updates flight-plan "${pending[@]}"
}

