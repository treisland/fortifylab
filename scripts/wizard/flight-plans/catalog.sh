# shellcheck shell=bash
# Module: flight-plans/catalog
# Responsibility: Flight Plan tool access, catalog records, labels, selection, and alignment summaries.
# Layer: operation
# Requires: python3, FORTIFY_HOME_K8S, ENV_FILE, env_get_value.
# Exports: flight_plan catalog and comparison helpers.
# Side effects: Reads Flight Plan catalogs and environment configuration.
# Interactive: no.
[ -n "${FORTIFY_WIZARD_FLIGHT_PLAN_CATALOG_LOADED:-}" ] && return 0
FORTIFY_WIZARD_FLIGHT_PLAN_CATALOG_LOADED=1

flight_plan_tool() {
    local tool root
    tool="$FORTIFY_HOME_K8S/scripts/tools/flight-plans.py"
    if [ ! -f "$tool" ]; then
        root="${FORTIFY_WIZARD_SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
        tool="$root/scripts/tools/flight-plans.py"
    fi
    python3 "$tool" "$@"
}

flight_plan_default_id() {
    flight_plan_tool default 2>/dev/null || printf '%s\n' fortify-26.2
}

flight_plan_selected_id() {
    printf '%s\n' "${FORTIFY_FLIGHT_PLAN:-$(flight_plan_default_id)}"
}

flight_plan_list_records() {
    local include="${1:-}"
    if [ "$include" = candidate ] || [ "$include" = candidates ] || [ "$include" = all ] || [ "$include" = "--include-candidates" ]; then
        flight_plan_tool list --include-candidates 2>/dev/null
    else
        flight_plan_tool list 2>/dev/null
    fi
}

flight_plan_local_records() {
    flight_plan_tool list --local-only 2>/dev/null
}

flight_plan_status_label() {
    case "$1" in
        recommended) printf '%s\n' Recommended ;;
        known-good) printf '%s\n' Known-good ;;
        legacy) printf '%s\n' Legacy ;;
        deprecated) printf '%s\n' Deprecated ;;
        candidate) printf '%s\n' Candidate ;;
        *) printf '%s\n' "${1:-Unknown}" ;;
    esac
}

flight_plan_label_for_id() {
    local plan_id="$1" record id label status family
    while IFS= read -r record; do
        IFS=$'	' read -r id label status family <<<"$record"
        [ "$id" = "$plan_id" ] || continue
        printf '%s
' "${label:-$plan_id}"
        return 0
    done < <(flight_plan_list_records all)
    printf '%s
' "$plan_id"
}

flight_plan_pending_value() {
    local key="$1" fallback="${2:-}" pair
    shift 2 || true
    for pair in "$@"; do
        [ "${pair%%=*}" = "$key" ] || continue
        printf '%s\n' "${pair#*=}"
        return 0
    done
    printf '%s\n' "$fallback"
}

flight_plan_alignment_summary() {
    local plan_id="${1:-$(flight_plan_selected_id)}" output rc=0 drift=0 unknown=0 overrides=0
    output=$(flight_plan_tool compare-env "$plan_id" --env-file "$ENV_FILE" 2>/dev/null) || rc=$?
    [ -n "$output" ] || { printf 'unknown\n'; return 0; }
    drift=$(printf '%s\n' "$output" | awk -F'\t' '$2=="drifted" {c++} END{print c+0}')
    unknown=$(printf '%s\n' "$output" | awk -F'\t' '$2=="unknown" {c++} END{print c+0}')
    if [ "$unknown" -gt 0 ]; then
        printf 'needs review\n'
    elif [ "$drift" -gt 0 ] || [ "$rc" -ne 0 ]; then
        overrides="$drift"
        printf 'mixed (%d override%s or drift%s)\n' "$overrides" "$([ "$overrides" -eq 1 ] || printf s)" "$([ "$overrides" -eq 1 ] || printf s)"
    else
        printf 'aligned\n'
    fi
}

flight_plan_current_status() {
    local plan_id="${1:-$(flight_plan_selected_id)}"
    printf '  Flight Plan:        %s\n' "$plan_id"
    printf '  Alignment:          %s\n' "$(flight_plan_alignment_summary "$plan_id")"
    printf '  Deployment profile: %s\n' "${GUIDED_DEPLOYMENT_PROFILE_LABEL:-$(guided_profile_label "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}")}"
}

flight_plan_show_comparison() {
    local plan_id="${1:-$(flight_plan_selected_id)}" output
    section "Flight Plan comparison"
    output=$(flight_plan_tool compare-env "$plan_id" --env-file "$ENV_FILE" 2>/dev/null || true)
    if [ -z "$output" ]; then
        error "Could not compare .env to Flight Plan $plan_id. Validate the catalog."
        return 1
    fi
    printf '  %-36s %-18s %-22s %s\n' "Key" "State" "Expected" "Current"
    printf '%s\n' "$output" | while IFS=$'\t' read -r key state expected current; do
        printf '  %-36s %-18s %-22s %s\n' "$key" "$state" "$expected" "$current"
    done
    cat <<'EOF'

Rollback note:
  Restoring a previous .env backup is configuration rollback only. It does not
  downgrade application data, database schemas, or persistent volumes.
EOF
}


