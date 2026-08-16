#!/usr/bin/env bash
# shellcheck shell=bash
# Compatibility wrappers for the dependency-free Flight Plans TOML/Python helper.

flight_plan_tool_path() {
    printf '%s/scripts/tools/flight-plans.py\n' "${FORTIFY_HOME_K8S:-$(pwd)}"
}

flight_plan_validate_catalog() {
    python3 "$(flight_plan_tool_path)" validate
}

flight_plan_list() {
    local include="${1:-}"
    if [ "$include" = "candidate" ] || [ "$include" = "all" ] || [ "$include" = "--include-candidates" ]; then
        python3 "$(flight_plan_tool_path)" list --include-candidates
    else
        python3 "$(flight_plan_tool_path)" list
    fi
}

flight_plan_env_updates() {
    python3 "$(flight_plan_tool_path)" env-updates "$@"
}

flight_plan_compare_env() {
    python3 "$(flight_plan_tool_path)" compare-env "$@"
}
