#!/bin/bash
# shellcheck disable=SC2016 # Password-file expansion intentionally occurs inside pods.
# Reusable, bounded dependency gates for Fortify component start scripts.
# Callers must load .env and set KUBECTL (defaults to MicroK8s).

FORTIFY_HEALTH_TIMEOUT="${FORTIFY_HEALTH_TIMEOUT:-600}"
FORTIFY_HEALTH_INTERVAL="${FORTIFY_HEALTH_INTERVAL:-5}"
KUBECTL="${KUBECTL:-microk8s kubectl}"

[[ "$FORTIFY_HEALTH_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || {
    printf 'ERROR: FORTIFY_HEALTH_TIMEOUT must be a positive integer.\n' >&2
    return 1 2>/dev/null || exit 1
}
[[ "$FORTIFY_HEALTH_INTERVAL" =~ ^([1-9][0-9]*|0\.[0-9]+)$ ]] || {
    printf 'ERROR: FORTIFY_HEALTH_INTERVAL must be a positive number.\n' >&2
    return 1 2>/dev/null || exit 1
}

health_error() {
    printf 'ERROR: %s\n' "$*" >&2
}

health_wait_for() {
    local description="$1" timeout="$2" probe="$3"
    local started=$SECONDS

    printf 'Waiting up to %ss for %s...\n' "$timeout" "$description"
    while [ $((SECONDS - started)) -lt "$timeout" ]; do
        if "$probe" >/dev/null 2>&1; then
            printf '%s is ready.\n' "$description"
            return 0
        fi
        sleep "$FORTIFY_HEALTH_INTERVAL"
    done

    health_error "$description did not become healthy within ${timeout}s. Fix the dependency, then retry this operation."
    return 1
}

health_statefulset_ready() {
    local statefulset="$1" namespace="${NAMESPACE:?NAMESPACE is required}"
    local desired ready current
    # shellcheck disable=SC2086
    desired=$($KUBECTL -n "$namespace" get statefulset "$statefulset" -o jsonpath='{.spec.replicas}' 2>/dev/null) || return 1
    # A deliberately stopped workload is not healthy.
    [ "${desired:-0}" -gt 0 ] || return 1
    # shellcheck disable=SC2086
    ready=$($KUBECTL -n "$namespace" get statefulset "$statefulset" -o jsonpath='{.status.readyReplicas}' 2>/dev/null) || return 1
    # shellcheck disable=SC2086
    current=$($KUBECTL -n "$namespace" get statefulset "$statefulset" -o jsonpath='{.status.currentReplicas}' 2>/dev/null) || return 1
    [ "${ready:-0}" -eq "$desired" ] && [ "${current:-0}" -eq "$desired" ]
}

health_service_endpoints_ready() {
    local service="$1" namespace="${NAMESPACE:?NAMESPACE is required}"
    local addresses
    # shellcheck disable=SC2086
    addresses=$($KUBECTL -n "$namespace" get endpoints "$service" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null) || return 1
    [ -n "$addresses" ]
}

health_ingress_host_ready() {
    local ingress="$1" host="$2" namespace="${NAMESPACE:?NAMESPACE is required}"
    local hosts
    # shellcheck disable=SC2086
    hosts=$($KUBECTL -n "$namespace" get ingress "$ingress" -o jsonpath='{.spec.rules[*].host}' 2>/dev/null) || return 1
    printf '%s\n' "$hosts" | tr ' ' '\n' | grep -Fxq "$host"
}

health_mysql_query() {
    # Resolve either supported Bitnami password contract inside the container.
    # Neither the value nor command output is returned to the caller.
    # shellcheck disable=SC2086
    $KUBECTL -n "$NAMESPACE" exec mysql-0 -- sh -c \
        'if [ -n "${MYSQL_ROOT_PASSWORD_FILE:-}" ] && [ -r "$MYSQL_ROOT_PASSWORD_FILE" ]; then password=$(cat "$MYSQL_ROOT_PASSWORD_FILE"); else password=${MYSQL_ROOT_PASSWORD:-}; fi; [ -n "$password" ] && MYSQL_PWD="$password" /opt/bitnami/mysql/bin/mysql --user=root --connect-timeout=5 --batch --skip-column-names --execute="SELECT 1"' \
        >/dev/null 2>&1
}

health_postgresql_query() {
    # shellcheck disable=SC2086
    $KUBECTL -n "$NAMESPACE" exec postgresql-0 -- sh -c \
        'PGPASSWORD="$(cat "$POSTGRES_POSTGRES_PASSWORD_FILE")" /opt/bitnami/postgresql/bin/psql --username=postgres --dbname=postgres --no-psqlrc --tuples-only --command="SELECT 1"' \
        >/dev/null 2>&1
}

health_http_status() {
    local url="$1" ca_args=() resolve_args=() status host
    [ -n "${ROOTCA_CERT:-}" ] && [ -r "$ROOTCA_CERT" ] && ca_args=(--cacert "$ROOTCA_CERT")
    # Fresh installs may not have client DNS yet. Route the configured ingress
    # hostname to the local node while preserving TLS SNI and the Host header.
    host="${url#*://}"
    host="${host%%/*}"
    host="${host%%:*}"
    [ -n "$host" ] && resolve_args=(--resolve "${host}:443:127.0.0.1")
    status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
        --noproxy '*' --connect-timeout 5 --max-time "${FORTIFY_HEALTH_HTTP_MAX_TIME:-10}" \
        "${ca_args[@]}" "${resolve_args[@]}" "$url" 2>/dev/null) || {
        printf '%s\n' curl-failed
        return 1
    }
    printf '%s\n' "$status"
}

health_http_url() {
    local url="$1" status
    status=$(health_http_status "$url") || return 1
    # Redirects and authentication responses prove the application is serving;
    # 5xx responses do not.
    [[ "$status" =~ ^[234][0-9][0-9]$ ]]
}

health_http_detail() {
    local url="$1" status
    status=$(health_http_status "$url") || {
        printf 'Could not connect to %s through local ingress.\n' "$url"
        return 0
    }
    if [[ "$status" =~ ^[234][0-9][0-9]$ ]]; then
        printf 'Application endpoint returned HTTP %s from %s.\n' "$status" "$url"
    elif [[ "$status" =~ ^5[0-9][0-9]$ ]]; then
        printf 'Application endpoint returned HTTP %s from %s; inspect the application pod logs and database migration state.\n' "$status" "$url"
    else
        printf 'Application endpoint returned HTTP %s from %s.\n' "$status" "$url"
    fi
}

health_mysql_ready() {
    health_wait_for "MySQL StatefulSet" "$FORTIFY_HEALTH_TIMEOUT" health_mysql_statefulset_probe &&
        health_wait_for "MySQL authenticated query" "$FORTIFY_HEALTH_TIMEOUT" health_mysql_query
}

health_mysql_statefulset_probe() { health_statefulset_ready mysql; }
health_postgresql_statefulset_probe() { health_statefulset_ready postgresql; }
health_ssc_statefulset_probe() { health_statefulset_ready ssc-webapp; }
health_ssc_service_probe() { health_service_endpoints_ready ssc-service; }
health_ssc_ingress_probe() { health_ingress_host_ready ssc-ingress "${SSC:?SSC is required}"; }
health_lim_statefulset_probe() { health_statefulset_ready lim; }
health_lim_service_probe() { health_service_endpoints_ready lim; }
health_lim_ingress_probe() { health_ingress_host_ready lim-ingress "${LIM:?LIM is required}"; }

health_postgresql_ready() {
    health_wait_for "PostgreSQL StatefulSet" "$FORTIFY_HEALTH_TIMEOUT" health_postgresql_statefulset_probe &&
        health_wait_for "PostgreSQL authenticated query" "$FORTIFY_HEALTH_TIMEOUT" health_postgresql_query
}

health_ssc_http_probe() { health_http_url "${SSC_URL:?SSC_URL is required}"; }
health_lim_http_probe() { health_http_url "${LIM_URL:?LIM_URL is required}"; }
health_dast_http_probe() { health_http_url "${SCDAST_URL:?SCDAST_URL is required}"; }

health_ssc_ready() {
    health_mysql_ready &&
        health_wait_for "SSC StatefulSet" "$FORTIFY_HEALTH_TIMEOUT" health_ssc_statefulset_probe &&
        health_wait_for "SSC service endpoints" "$FORTIFY_HEALTH_TIMEOUT" health_ssc_service_probe &&
        health_wait_for "SSC ingress host" "$FORTIFY_HEALTH_TIMEOUT" health_ssc_ingress_probe &&
        health_wait_for "SSC application endpoint" "$FORTIFY_HEALTH_TIMEOUT" health_ssc_http_probe
}

health_lim_ready() {
    health_wait_for "LIM StatefulSet" "$FORTIFY_HEALTH_TIMEOUT" health_lim_statefulset_probe &&
        health_wait_for "LIM service endpoints" "$FORTIFY_HEALTH_TIMEOUT" health_lim_service_probe &&
        health_wait_for "LIM ingress host" "$FORTIFY_HEALTH_TIMEOUT" health_lim_ingress_probe &&
        health_wait_for "LIM application endpoint" "$FORTIFY_HEALTH_TIMEOUT" health_lim_http_probe
}

health_dast_core_workloads_probe() {
    health_statefulset_ready sdast-core-scancentral-dast-core-api &&
        health_statefulset_ready sdast-core-scancentral-dast-core-globalservice &&
        health_statefulset_ready sdast-core-scancentral-dast-core-utilityservice
}

health_dast_core_ready() {
    health_wait_for "DAST Core workloads" "$FORTIFY_HEALTH_TIMEOUT" health_dast_core_workloads_probe &&
        health_wait_for "DAST API endpoint" "$FORTIFY_HEALTH_TIMEOUT" health_dast_http_probe
}
