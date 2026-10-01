# shellcheck shell=bash
# Module: flight-plans/menu
# Responsibility: Candidate discovery/local catalog management and interactive version menus.
# Layer: menu
# Requires: flight-plans/catalog, flight-plans/staging, environment editor helpers, UI helpers, FORTIFY_HOME_K8S, ENV_FILE.
# Exports: discovery, local catalog, component, and version menu functions.
# Side effects: May query Docker Hub and update local or environment configuration after confirmation.
# Interactive: yes.
[ -n "${FORTIFY_WIZARD_FLIGHT_PLAN_MENU_LOADED:-}" ] && return 0
FORTIFY_WIZARD_FLIGHT_PLAN_MENU_LOADED=1

flight_plan_show_candidates() {
    local records=() record plan_id label status family found=0
    section "Candidate Flight Plans"
    mapfile -t records < <(flight_plan_list_records all)
    for record in "${records[@]}"; do
        IFS=$'\t' read -r plan_id label status family <<<"$record"
        [ "$status" = candidate ] || continue
        printf '  %-18s %-18s family %s\n' "$plan_id" "$label" "$family"
        found=1
    done
    [ "$found" -eq 1 ] || note "No candidate Flight Plans are currently available."
}

flight_plan_component_select_menu() {
    local result_var="$1" choice component
    while true; do
        title "Component override"
        printf '\nSelected Flight Plan baseline: %s\n\n' "$(flight_plan_selected_id)"
        printf '  1. SSC  - %s\n' "$(flight_plan_component_drift_status ssc)"
        printf '  2. LIM  - %s\n' "$(flight_plan_component_drift_status lim)"
        printf '  3. SAST - %s\n' "$(flight_plan_component_drift_status sast)"
        printf '  4. DAST - %s\n' "$(flight_plan_component_drift_status dast)"
        printf '\n  b. Back\n\n'
        ask choice "Select component:"
        case "$choice" in
            1) component=ssc ;;
            2) component=lim ;;
            3) component=sast ;;
            4) component=dast ;;
            [Bb]|"") return 0 ;;
            *) error "Select SSC, LIM, SAST, or DAST."; sleep 1; continue ;;
        esac
        printf -v "$result_var" '%s' "$component"
        return 0
    done
}

flight_plan_component_manual_values() {
    local array_name="$1" component="$2" key current value changed=0
    while IFS= read -r key; do
        [ -n "$key" ] || continue
        current=$(env_current_value "$key")
        printf '\n%s [%s]\n' "$key" "${current:-<unset>}"
        read -rp "New value (empty to keep current): " value
        [ -n "$value" ] || continue
        env_pending_set "$array_name" "$key" "$value"
        changed=1
    done < <(flight_plan_component_keys "$component")
    if [ "$changed" -eq 1 ]; then
        flight_plan_stage_drift_marker "$array_name" "$component"
        note "$(flight_plan_component_label "$component") override staged and marked as Flight Plan drift."
    else
        note "No component values were changed."
    fi
}

flight_plan_component_override_menu() {
    local array_name="$1" component choice target_plan
    flight_plan_component_select_menu component || return $?
    [ -n "$component" ] || return 0
    while true; do
        title "$(flight_plan_component_label "$component") override"
        flight_plan_print_component_impact "$component" "$(flight_plan_selected_id)"
        flight_plan_component_override_safety_note
        cat <<'EOF'

Options
  1. Stage this component from a target Flight Plan
  2. Enter manual component values
  3. Restore this component to current Flight Plan baseline
  p. Preview pending changes
  a. Apply pending version changes

  b. Back
EOF
        echo
        ask choice "Select:"
        case "$choice" in
            1)
                target_plan=""
                flight_plan_choose_menu target_plan all || continue
                [ -n "$target_plan" ] || continue
                section "Component impact"
                flight_plan_print_component_impact "$component" "$target_plan"
                if confirm "Stage $(flight_plan_component_label "$component") values from $target_plan?"; then
                    if flight_plan_stage_component_from_plan "$array_name" "$component" "$target_plan"; then
                        flight_plan_stage_drift_marker "$array_name" "$component"
                        note "$(flight_plan_component_label "$component") staged from $target_plan and marked as Flight Plan drift."
                    else
                        error "$(flight_plan_component_label "$component") has no populated values in $target_plan. Nothing was staged."
                    fi
                fi
                press_any
                ;;
            2) flight_plan_component_manual_values "$array_name" "$component"; press_any ;;
            3)
                section "Restore baseline"
                flight_plan_print_component_impact "$component" "$(flight_plan_selected_id)"
                if confirm "Restore $(flight_plan_component_label "$component") to current Flight Plan baseline?"; then
                    flight_plan_restore_component_baseline "$array_name" "$component" "$(flight_plan_selected_id)"
                    flight_plan_clear_drift_marker "$array_name" "$component"
                    note "$(flight_plan_component_label "$component") restore staged."
                fi
                press_any
                ;;
            [Pp])
                local -n pending_ref="$array_name"
                [ "${#pending_ref[@]}" -gt 0 ] && env_preview_changes "${pending_ref[@]}" || note "No pending changes."
                press_any
                ;;
            [Aa]) env_section_apply_pending flight-plan-component "$array_name"; press_any ;;
            [Bb]|"") return 0 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

flight_plan_discovery_menu() {
    local family output
    title "Flight Plan Discovery"
    cat <<'EOF'

Discover -> Draft -> Review -> Test -> Add (below)

Discovery queries Docker Hub for known Fortify repositories and writes a
candidate TOML file under tmp/flight-plan-candidates/. It never updates any
catalog by itself. From here you (or the repo owner) can either add the
candidate to your own local Flight Plans, or -- for repo owners -- promote it
into the shared curated catalog for everyone.
EOF
    echo
    ask family "Fortify family to discover, for example 26.2 or 25:"
    [ -n "$family" ] || return 0
    output="$FORTIFY_HOME_K8S/tmp/flight-plan-candidates/fortify-$family.toml"
    flight_plan_tool discover --family "$family" --output "$output"
    echo
    note "Next step: add this candidate to your own local Flight Plans (never committed, never touches the shared catalog)."
    if confirm "Add fortify-$family to your local Flight Plans now?"; then
        flight_plan_promote_local_menu "$family"
        return 0
    fi
    note "You can add it later from 'Add a discovered candidate to my local Flight Plans' (option 9)."
    press_any
}

flight_plan_promote_local_menu() {
    local family="${1:-}" candidate_path status
    title "Add to my local Flight Plans"
    cat <<'EOF'

This adds a Flight Plan to your own local catalog
(config/flight-plans.local.toml), which is never committed to git and never
changes the shared, repo-owner-curated catalog. Use this to try a release the
repo owner has not reviewed yet -- it then shows up alongside curated plans
everywhere you pick a Flight Plan.

First run "Refresh/discover candidate Flight Plan tags" for the release you
want, then come back here to add it.
EOF
    echo
    if [ -z "$family" ]; then
        ask family "Fortify family already discovered, for example 26.3:"
    fi
    [ -n "$family" ] || return 0
    candidate_path="$FORTIFY_HOME_K8S/tmp/flight-plan-candidates/fortify-$family.toml"
    if [ ! -f "$candidate_path" ]; then
        error "No candidate file found at $candidate_path. Run discovery first."
        press_any
        return 0
    fi
    section "Candidate to add"
    sed 's/^/  /' "$candidate_path" 2>/dev/null
    echo
    section "Status for your local Flight Plan"
    echo "  1. candidate (default)"
    echo "  2. known-good"
    echo "  3. legacy"
    echo "  4. deprecated"
    echo
    local status_choice
    ask status_choice "Select:"
    case "$status_choice" in
        ""|1) status=candidate ;;
        2) status=known-good ;;
        3) status=legacy ;;
        4) status=deprecated ;;
        *) error "Invalid selection; defaulting to candidate."; status=candidate ;;
    esac
    if confirm "Add fortify-$family to your local Flight Plans as '$status'?"; then
        flight_plan_tool promote-local "$candidate_path" --status "$status" --yes
    else
        note "Not added."
    fi
    press_any
}

flight_plan_remove_local_menu() {
    local records=() record plan_id label status family idx choice
    title "Remove a local Flight Plan"
    cat <<'EOF'

This removes a Flight Plan from your own local catalog
(config/flight-plans.local.toml), which is never committed to git. It never
touches the shared, repo-owner-curated catalog -- only plans you added with
"Add a discovered candidate to my local Flight Plans" show up here.
EOF
    echo
    mapfile -t records < <(flight_plan_local_records)
    if [ "${#records[@]}" -eq 0 ]; then
        note "You have no local Flight Plans to remove."
        press_any
        return 0
    fi
    section "Your local Flight Plans"
    for idx in "${!records[@]}"; do
        IFS=$'\t' read -r plan_id label status family <<<"${records[$idx]}"
        printf '  %2d. %-18s %-13s %s\n' "$((idx + 1))" "$label" "$(flight_plan_status_label "$status")" "family $family"
    done
    cat <<'EOF'

  b. Back
EOF
    echo
    ask choice "Select a Flight Plan to remove:"
    case "$choice" in
        [Bb]|"") return 0 ;;
        ''|*[!0-9]*) error "Select a Flight Plan number shown above."; press_any; return 0 ;;
    esac
    if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#records[@]}" ]; then
        error "Out of range"
        press_any
        return 0
    fi
    IFS=$'\t' read -r plan_id label status family <<<"${records[$((choice - 1))]}"
    if confirm "Remove '$label' ($plan_id) from your local Flight Plans? This cannot be undone."; then
        flight_plan_tool remove-local "$plan_id" --yes
    else
        note "Not removed."
    fi
    press_any
}

flight_plan_versions_menu() {
    local choice pending_updates=()
    while true; do
        title "Deployment Versions"
        cat <<'EOF'

Purpose
  Choose a Fortify Flight Plan or override individual component versions.
EOF
        section "Current configuration"
        flight_plan_current_status
        section "Fortify components"
        grep -E '^\s*export\s+FORTIFY_(SSC|SCSAST|SCDAST|LIM|FLIGHT_PLAN)' "$ENV_FILE" 2>/dev/null | sed 's/^\s*export\s*/  /' || true
        section "Database versions"
        grep -E '^\s*export\s+FORTIFY_(MYSQL|POSTGRES)' "$ENV_FILE" 2>/dev/null | sed 's/^\s*export\s*/  /' || true
        cat <<'EOF'

Impact
  Flight Plans align Fortify product versions. MySQL and PostgreSQL are managed
  separately because application upgrades and database rollback are different risks.
EOF
        section "Core actions"
        echo "   1. Upgrade full Flight Plan"
        echo "   2. Select Fortify Flight Plan"
        echo "   3. Preview a Flight Plan's versions"
        section "Discover new releases"
        echo "   4. Show candidate Flight Plans"
        echo "   5. Refresh/discover candidate Flight Plan tags"
        echo "   6. Add a discovered candidate to my local Flight Plans"
        echo "   7. Remove a local Flight Plan"
        section "Advanced (expert)"
        echo "   8. Advanced individual component override"
        echo "   9. Override all Fortify component version fields"
        echo "  10. Manage database versions"
        section "Review and apply"
        echo "  11. Compare .env to selected Flight Plan"
        echo "  12. Preview pending .env changes"
        echo "  13. Apply pending version changes"
        echo
        echo "   r. Return"
        echo "   q. Quit safely"
        echo
        ask choice "Select:"
        case "$choice" in
            1) flight_plan_full_upgrade_flow pending_updates; press_any ;;
            2) flight_plan_select_menu pending_updates ;;
            3) flight_plan_preview_menu all ;;
            4) flight_plan_show_candidates; press_any ;;
            5) flight_plan_discovery_menu ;;
            6) flight_plan_promote_local_menu ;;
            7) flight_plan_remove_local_menu ;;
            8) flight_plan_component_override_menu pending_updates || return $? ;;
            9) env_guided_section_editor "Individual Fortify component versions" versions || return $? ;;
            10) env_guided_section_editor "Database versions" database_versions || return $? ;;
            11) flight_plan_show_comparison; press_any ;;
            12) [ "${#pending_updates[@]}" -gt 0 ] && env_preview_changes "${pending_updates[@]}" || note "No pending changes."; press_any ;;
            13) env_section_apply_pending flight-plan pending_updates; press_any ;;
            [Rr]) env_section_prompt_return pending_updates && return 0 ;;
            [Qq]) env_section_prompt_return pending_updates && return 130 ;;
            *) error "Invalid selection"; sleep 1 ;;
        esac
    done
}

versions_menu() {
    flight_plan_versions_menu
}

