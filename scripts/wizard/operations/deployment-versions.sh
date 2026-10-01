#!/usr/bin/env bash
# shellcheck shell=bash
# Module: operations/deployment-versions
# Responsibility: Define environment sections and discover/cache recommended deployment versions.
# Requires: FORTIFY_HOME_K8S; env_current_value, env_pending_set; section, note,
#           confirm; curl and python3 for online discovery.
# Exports: env_section_keys and deployment_version_* functions.
# Side effects: Reads ENV_FILE, queries Docker Hub, and writes the wizard cache.
# Interactive: deployment_versions_discover_into prompts before staging values.

if [[ -n "${FORTIFYLAB_WIZARD_DEPLOYMENT_VERSIONS_LOADED:-}" ]]; then
    return 0
fi
FORTIFYLAB_WIZARD_DEPLOYMENT_VERSIONS_LOADED=1

env_section_keys() {
    case "$1" in
        identity) printf '%s\n' NAMESPACE ;;
        urls) printf '%s\n' SSC LIM SCDAST SCSAST SSC_URL LIM_URL LIM_API_URL SCDAST_URL SCSAST_URL SCSAST_CTRL_URL ;;
        versions) printf '%s\n' FORTIFY_FLIGHT_PLAN FORTIFY_SSC_CHART_VERSION FORTIFY_SSC_IMAGE_TAG FORTIFY_SCSAST_CHART_VERSION FORTIFY_SCSAST_CTRL_IMAGE_TAG FORTIFY_SCSAST_WORKER_IMAGE_TAG FORTIFY_SCDAST_CHART_VERSION FORTIFY_LIM_CHART_VERSION ;;
        database_versions) printf '%s\n' FORTIFY_MYSQL_CHART_VERSION FORTIFY_POSTGRES_CHART_VERSION FORTIFY_POSTGRES_IMAGE_TAG FORTIFY_MYSQL_IMAGE_TAG ;;
        credentials) printf '%s\n' DEFAULT_PASS SCDAST_SSC_USER SCDAST_SSC_PASS SCDAST_DB_OWNER_USER SCDAST_DB_OWNER_PASS SCDAST_DB_STANDARD_USER SCDAST_DB_STANDARD_PASS LIM_POOL_NAME LIM_POOL_PASS ;;
        *) return 1 ;;
    esac
}


deployment_version_cache_dir() {
    printf '%s\n' "${FORTIFY_HOME_K8S:-.}/.fortifylab/version-cache"
}

deployment_version_recommended_value() {
    local key="$1"
    sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$key=\"?([^\"]*)\"?[[:space:]]*$/\2/p" "$FORTIFY_HOME_K8S/.env.example" 2>/dev/null | tail -n 1
}

deployment_version_repo_for_key() {
    case "$1" in
        FORTIFY_SSC_CHART_VERSION) printf '%s\n' fortifydocker/helm-ssc ;;
        FORTIFY_SSC_IMAGE_TAG) printf '%s\n' fortifydocker/ssc-webapp ;;
        FORTIFY_SCSAST_CHART_VERSION) printf '%s\n' fortifydocker/helm-scancentral-sast ;;
        FORTIFY_SCDAST_CHART_VERSION) printf '%s\n' fortifydocker/helm-scancentral-dast-core ;;
        FORTIFY_LIM_CHART_VERSION) printf '%s\n' fortifydocker/helm-lim ;;
        FORTIFY_MYSQL_CHART_VERSION) printf '%s\n' bitnamicharts/mysql ;;
        FORTIFY_POSTGRES_CHART_VERSION) printf '%s\n' bitnamicharts/postgresql ;;
        FORTIFY_MYSQL_IMAGE_TAG) printf '%s\n' bitnamilegacy/mysql ;;
        FORTIFY_POSTGRES_IMAGE_TAG) printf '%s\n' bitnamilegacy/postgresql ;;
        *) return 1 ;;
    esac
}

deployment_version_cached_latest() {
    local key="$1" file
    file="$(deployment_version_cache_dir)/$key.latest"
    [ -s "$file" ] && sed -n '1p' "$file"
}

deployment_version_cache_latest() {
    local key="$1" value="$2" dir
    [ -n "$value" ] || return 0
    dir=$(deployment_version_cache_dir)
    mkdir -p "$dir" || return 0
    printf '%s\n' "$value" >"$dir/$key.latest" 2>/dev/null || true
}

deployment_version_query_dockerhub_latest() {
    local repo="$1"
    command -v curl >/dev/null 2>&1 || return 1
    command -v python3 >/dev/null 2>&1 || return 1
    curl -fsSL "https://registry.hub.docker.com/v2/repositories/$repo/tags?page_size=25&ordering=last_updated" 2>/dev/null | python3 -c '
import json, re, sys
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(1)
for item in data.get("results", []):
    name=item.get("name", "")
    if name and name != "latest" and re.search(r"[0-9]", name):
        print(name)
        sys.exit(0)
sys.exit(1)
'
}

deployment_version_latest_for_key() {
    local key="$1" repo latest
    repo=$(deployment_version_repo_for_key "$key" 2>/dev/null) || return 1
    latest=$(deployment_version_query_dockerhub_latest "$repo" 2>/dev/null || true)
    if [ -n "$latest" ]; then
        deployment_version_cache_latest "$key" "$latest"
        printf '%s\n' "$latest"
        return 0
    fi
    deployment_version_cached_latest "$key"
}

deployment_versions_status() {
    local key current recommended cached repo
    section "Deployment version guidance"
    printf '  %-36s %-20s %-20s %-20s\n' "Key" "Current" "Recommended" "Cached/latest"
    while IFS= read -r key; do
        current=$(env_current_value "$key")
        recommended=$(deployment_version_recommended_value "$key")
        cached=$(deployment_version_cached_latest "$key")
        repo=$(deployment_version_repo_for_key "$key" 2>/dev/null || true)
        [ -n "$cached" ] || cached="<not checked>"
        [ -n "$recommended" ] || recommended="<unknown>"
        printf '  %-36s %-20s %-20s %-20s\n' "$key" "${current:-<unset>}" "$recommended" "$cached"
        [ -n "$repo" ] || printf '    note: no online source is mapped for %s; use manual entry.\n' "$key"
    done < <(env_section_keys versions)
    cat <<'EOF'

Use 'u' in the Flight Plans and upgrades editor to check available Docker Hub tags.
Newest available is not automatically compatible; review Fortify release notes
and database upgrade boundaries before applying version changes.
EOF
}

deployment_versions_discover_into() {
    local array_name="$1" key latest found=0 keys=()
    section "Checking available deployment versions"
    mapfile -t keys < <(env_section_keys versions)
    for key in "${keys[@]}"; do
        latest=$(deployment_version_latest_for_key "$key" 2>/dev/null || true)
        if [ -n "$latest" ]; then
            printf '  %-36s latest available: %s
' "$key" "$latest"
            if confirm "Queue $key=$latest?"; then
                env_pending_set "$array_name" "$key" "$latest"
            fi
            found=1
        else
            printf '  %-36s no online value found; use manual entry.
' "$key"
        fi
    done
    [ "$found" -eq 1 ] || note "No online version data was available. Manual entry remains available by selecting a numbered field."
}

