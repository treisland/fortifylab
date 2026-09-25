#!/usr/bin/env bash
# shellcheck shell=bash
# Deployed-versus-configured Fortify component versions.
#
# .env says which versions a lab should run; this library reads which versions
# the cluster actually runs (Helm chart versions and StatefulSet image tags) so
# the wizard can mark components that need a redeploy after a Flight Plan
# change. Results are cached in .fortifylab/deployed-versions because each
# collection costs several kubectl/helm calls.
#
# Cache format (KEY=VALUE per line):
#   checked_at=<epoch seconds>
#   state=ok|unreachable
#   FORTIFY_SSC_CHART_VERSION=26.2.0-1          (and the other running values)
#   SCDAST_CORE_CHART_VERSION / SCDAST_SCANNER_CHART_VERSION
#
# A Helm release that is not in the deployed state is recorded as
# "<status>:<chart version>" so it never compares equal to .env.
#
# Set FORTIFY_DEPLOYED_VERSIONS=off to disable cluster lookups entirely
# (every status then reports unknown, and callers fall back to health only).

DEPLOYED_VERSIONS_TTL="${DEPLOYED_VERSIONS_TTL:-15}"

deployed_versions_cache_path() {
    printf '%s/.fortifylab/deployed-versions\n' "${FORTIFY_HOME_K8S:-.}"
}

deployed_versions_enabled() {
    [ "${FORTIFY_DEPLOYED_VERSIONS:-on}" != off ]
}

deployed_versions_invalidate() {
    rm -f "$(deployed_versions_cache_path)" 2>/dev/null || true
}

# Checks: id|deployed key in the cache|configured .env key|label.
deployed_version_checks() {
    cat <<'EOF'
ssc_chart|FORTIFY_SSC_CHART_VERSION|FORTIFY_SSC_CHART_VERSION|SSC chart
ssc_image|FORTIFY_SSC_IMAGE_TAG|FORTIFY_SSC_IMAGE_TAG|SSC image
lim_chart|FORTIFY_LIM_CHART_VERSION|FORTIFY_LIM_CHART_VERSION|LIM chart
sast_chart|FORTIFY_SCSAST_CHART_VERSION|FORTIFY_SCSAST_CHART_VERSION|SAST chart
sast_ctrl_image|FORTIFY_SCSAST_CTRL_IMAGE_TAG|FORTIFY_SCSAST_CTRL_IMAGE_TAG|SAST controller image
sast_worker_image|FORTIFY_SCSAST_WORKER_IMAGE_TAG|FORTIFY_SCSAST_WORKER_IMAGE_TAG|SAST sensor image
dast_core_chart|SCDAST_CORE_CHART_VERSION|FORTIFY_SCDAST_CHART_VERSION|DAST core chart
dast_scanner_chart|SCDAST_SCANNER_CHART_VERSION|FORTIFY_SCDAST_CHART_VERSION|DAST scanner chart
EOF
}

# Which checks decide a Flight Plan component (ssc|lim|sast|dast) or a guided
# step id. Steps that are not Fortify products have no checks.
deployed_checks_for() {
    case "$1" in
        ssc) printf '%s\n' ssc_chart ssc_image ;;
        lim) printf '%s\n' lim_chart ;;
        sast_controller) printf '%s\n' sast_chart sast_ctrl_image ;;
        sast|sast_sensor) printf '%s\n' sast_chart sast_ctrl_image sast_worker_image ;;
        dast_core) printf '%s\n' dast_core_chart ;;
        dast_scanner) printf '%s\n' dast_scanner_chart ;;
        dast) printf '%s\n' dast_core_chart dast_scanner_chart ;;
        *) return 0 ;;
    esac
}

# Redeploy order: SAST and DAST register with SSC, DAST needs LIM.
deployed_components_in_order() {
    printf '%s\n' ssc lim sast dast
}

deployed_versions_image_tag() {
    local statefulset="$1" image
    # shellcheck disable=SC2086
    image=$($KUBECTL -n "$NAMESPACE" get statefulset "$statefulset" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null) || return 1
    [ -n "$image" ] || return 1
    case "${image##*/}" in
        *:*) printf '%s\n' "${image##*:}" ;;
        *) printf '%s\n' latest ;;
    esac
}

deployed_versions_sensor_names() {
    if declare -F fortify_sast_sensor_statefulset_names >/dev/null 2>&1; then
        fortify_sast_sensor_statefulset_names
    else
        printf '%s\n' scancentral-sast-sensor-linux scancentral-sast-sensor scancentral-sast-worker-linux
    fi
}

deployed_versions_write_unreachable() {
    local cache="$1"
    printf 'checked_at=%s\nstate=unreachable\n' "$(date +%s)" >"$cache"
}

deployed_versions_refresh() {
    local cache tmp helm_json tag name
    deployed_versions_enabled || return 1
    cache=$(deployed_versions_cache_path)
    mkdir -p "$(dirname "$cache")" 2>/dev/null || return 1
    if [ -z "${KUBECTL:-}" ] || [ -z "${HELM:-}" ] || [ -z "${NAMESPACE:-}" ]; then
        deployed_versions_write_unreachable "$cache"
        return 1
    fi
    # shellcheck disable=SC2086
    if ! helm_json=$($HELM -n "$NAMESPACE" list --all -o json 2>/dev/null) || [ -z "$helm_json" ]; then
        deployed_versions_write_unreachable "$cache"
        return 1
    fi
    tmp="$cache.tmp.$$"
    {
        printf 'checked_at=%s\nstate=ok\n' "$(date +%s)"
        printf '%s' "$helm_json" | python3 -c '
import json, re, sys
keys = {
    "ssc": "FORTIFY_SSC_CHART_VERSION",
    "lim": "FORTIFY_LIM_CHART_VERSION",
    "scancentral-sast": "FORTIFY_SCSAST_CHART_VERSION",
    "sdast-core": "SCDAST_CORE_CHART_VERSION",
    "sdast-scanner": "SCDAST_SCANNER_CHART_VERSION",
}
try:
    releases = json.load(sys.stdin) or []
except json.JSONDecodeError:
    releases = []
values = {}
for release in releases:
    key = keys.get(release.get("name", ""))
    if not key:
        continue
    match = re.match(r"^.*?-(\d.*)$", str(release.get("chart", "")))
    if not match:
        continue
    version = match.group(1)
    status = str(release.get("status", "deployed"))
    values[key] = version if status == "deployed" else f"{status}:{version}"
core = values.get("SCDAST_CORE_CHART_VERSION", "")
scanner = values.get("SCDAST_SCANNER_CHART_VERSION", "")
if core or scanner:
    values["FORTIFY_SCDAST_CHART_VERSION"] = core if core == scanner or not scanner else (scanner if not core else f"mixed:{core}/{scanner}")
for key, value in values.items():
    print(f"{key}={value}")
'
        tag=$(deployed_versions_image_tag ssc-webapp) && printf 'FORTIFY_SSC_IMAGE_TAG=%s\n' "$tag"
        tag=$(deployed_versions_image_tag scancentral-sast-controller) && printf 'FORTIFY_SCSAST_CTRL_IMAGE_TAG=%s\n' "$tag"
        for name in $(deployed_versions_sensor_names); do
            if tag=$(deployed_versions_image_tag "$name"); then
                printf 'FORTIFY_SCSAST_WORKER_IMAGE_TAG=%s\n' "$tag"
                break
            fi
        done
    } >"$tmp" && mv "$tmp" "$cache"
}

deployed_versions_cache_value() {
    local key="$1" cache line
    cache=$(deployed_versions_cache_path)
    [ -f "$cache" ] || return 1
    while IFS= read -r line; do
        [ "${line%%=*}" = "$key" ] || continue
        printf '%s\n' "${line#*=}"
        return 0
    done <"$cache"
    return 1
}

deployed_versions_age() {
    local checked
    checked=$(deployed_versions_cache_value checked_at) || return 1
    [[ "$checked" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "$(( $(date +%s) - checked ))"
}

# Refresh when the cache is missing or older than max_age seconds.
deployed_versions_ensure_fresh() {
    local max_age="${1:-$DEPLOYED_VERSIONS_TTL}" age
    deployed_versions_enabled || return 1
    age=$(deployed_versions_age 2>/dev/null) || { deployed_versions_refresh; return; }
    [ "$age" -le "$max_age" ] && return 0
    deployed_versions_refresh
}

deployed_versions_state() {
    deployed_versions_enabled || { printf 'unknown\n'; return 0; }
    deployed_versions_cache_value state 2>/dev/null || printf 'unknown\n'
}

deployed_configured_value() {
    local key="$1"
    printf '%s\n' "${!key:-}"
}

deployed_check_line() {
    local wanted="$1" id deployed_key configured_key label
    while IFS='|' read -r id deployed_key configured_key label; do
        [ "$id" = "$wanted" ] || continue
        printf '%s|%s|%s\n' "$deployed_key" "$configured_key" "$label"
        return 0
    done < <(deployed_version_checks)
    return 1
}

# current | stale | not-deployed | unknown. Reads the cache as it is.
deployed_check_status() {
    local check="$1" line deployed_key configured_key deployed configured
    [ "$(deployed_versions_state)" = ok ] || { printf 'unknown\n'; return 0; }
    line=$(deployed_check_line "$check") || { printf 'unknown\n'; return 0; }
    IFS='|' read -r deployed_key configured_key _ <<<"$line"
    configured=$(deployed_configured_value "$configured_key")
    [ -n "$configured" ] || { printf 'unknown\n'; return 0; }
    deployed=$(deployed_versions_cache_value "$deployed_key" 2>/dev/null || true)
    if [ -z "$deployed" ]; then
        printf 'not-deployed\n'
    elif [ "$deployed" = "$configured" ]; then
        printf 'current\n'
    else
        printf 'stale\n'
    fi
}

# Aggregate for a component or guided step:
# current | needs-redeploy | not-deployed | unknown | n/a.
# A check that is not deployed (for example SAST workers in a
# controller-only profile) does not make a deployed component stale.
deployed_status_for() {
    local target="$1" check status any=0 current=0 missing=0 unknown=0
    while IFS= read -r check; do
        [ -n "$check" ] || continue
        any=1
        status=$(deployed_check_status "$check")
        case "$status" in
            stale) printf 'needs-redeploy\n'; return 0 ;;
            current) current=$((current + 1)) ;;
            not-deployed) missing=$((missing + 1)) ;;
            *) unknown=$((unknown + 1)) ;;
        esac
    done < <(deployed_checks_for "$target")
    if [ "$any" -eq 0 ]; then
        printf 'n/a\n'
    elif [ "$current" -gt 0 ]; then
        printf 'current\n'
    elif [ "$missing" -gt 0 ] && [ "$unknown" -eq 0 ]; then
        printf 'not-deployed\n'
    else
        printf 'unknown\n'
    fi
}

# "<label> <running> -> <configured>" for each stale check, joined by "; ".
deployed_stale_detail() {
    local target="$1" check line deployed_key configured_key label detail=""
    while IFS= read -r check; do
        [ -n "$check" ] || continue
        [ "$(deployed_check_status "$check")" = stale ] || continue
        line=$(deployed_check_line "$check") || continue
        IFS='|' read -r deployed_key configured_key label <<<"$line"
        detail="${detail:+$detail; }$label $(deployed_versions_cache_value "$deployed_key") -> $(deployed_configured_value "$configured_key")"
    done < <(deployed_checks_for "$target")
    printf '%s\n' "$detail"
}

# Components (ssc lim sast dast, in redeploy order) that run a version other
# than the one configured in .env.
deployed_components_needing_redeploy() {
    local component
    while IFS= read -r component; do
        [ "$(deployed_status_for "$component")" = needs-redeploy ] && printf '%s\n' "$component"
    done < <(deployed_components_in_order)
}

# The Flight Plan the running versions match: a plan id, custom, or unknown.
deployed_flight_plan() {
    local tool
    [ "$(deployed_versions_state)" = ok ] || { printf 'unknown\n'; return 0; }
    tool="${FORTIFY_HOME_K8S:-.}/scripts/tools/flight-plans.py"
    python3 "$tool" match-running --values-file "$(deployed_versions_cache_path)" 2>/dev/null || printf 'unknown\n'
}

deployed_age_text() {
    local age
    age=$(deployed_versions_age 2>/dev/null) || { printf 'not checked\n'; return 0; }
    if [ "$age" -lt 60 ]; then
        printf 'checked just now\n'
    elif [ "$age" -lt 3600 ]; then
        printf 'checked %d min ago\n' "$((age / 60))"
    else
        printf 'checked %d h ago\n' "$((age / 3600))"
    fi
}

# One-line banner for the top of every wizard screen. Reads the cache only;
# never queries the cluster, so screens stay fast.
deployed_versions_banner() {
    local selected deployed stale=() component total=0 count label
    selected="${FORTIFY_FLIGHT_PLAN:-}"
    [ -n "$selected" ] || return 0
    case "$(deployed_versions_state)" in
        ok) ;;
        unreachable)
            printf 'Flight Plan %s · deployed version unknown (cluster unreachable, %s)\n' "$selected" "$(deployed_age_text)"
            return 0
            ;;
        *)
            deployed_versions_enabled || return 0
            printf 'Flight Plan %s · deployed version not checked yet\n' "$selected"
            return 0
            ;;
    esac
    while IFS= read -r component; do
        case "$(deployed_status_for "$component")" in
            needs-redeploy) stale+=("$component"); total=$((total + 1)) ;;
            current) total=$((total + 1)) ;;
        esac
    done < <(deployed_components_in_order)
    deployed=$(deployed_flight_plan)
    [ "$deployed" = custom ] && deployed="custom versions"
    if [ "$total" -eq 0 ]; then
        printf 'Flight Plan %s · no Fortify products deployed yet (%s)\n' "$selected" "$(deployed_age_text)"
        return 0
    fi
    count="${#stale[@]}"
    if [ "$count" -eq 0 ]; then
        printf 'Flight Plan %s · deployed and current (%s)\n' "$selected" "$(deployed_age_text)"
        return 0
    fi
    label=$(printf '%s\n' "${stale[@]}" | tr 'a-z' 'A-Z' | paste -sd, - | sed 's/,/, /g')
    printf 'Flight Plan: selected %s · running %s · %d of %d products need redeploy (%s) · %s\n' \
        "$selected" "$deployed" "$count" "$total" "$label" "$(deployed_age_text)"
}
