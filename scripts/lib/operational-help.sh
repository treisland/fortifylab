#!/usr/bin/env bash

# Read-only operational help for the Fortify lab wizard. Source this file from
# an interactive caller; no function runs automatically and no cluster object
# is mutated. Diagnostic bundle creation only writes to the requested output
# directory.

FORTIFY_OPERATION_TIMEOUT="${FORTIFY_OPERATION_TIMEOUT:-10}"
FORTIFY_OPERATION_HTTP_TIMEOUT="${FORTIFY_OPERATION_HTTP_TIMEOUT:-3}"
FORTIFY_OPERATION_NAMESPACE="${NAMESPACE:-fortify}"
FORTIFY_OPERATION_KUBECTL="${FORTIFY_OPERATION_KUBECTL:-microk8s kubectl}"
FORTIFY_RECOMMENDED_MEMORY_GIB="${FORTIFY_RECOMMENDED_MEMORY_GIB:-16}"
FORTIFY_RECOMMENDED_DISK_GIB="${FORTIFY_RECOMMENDED_DISK_GIB:-50}"

operational_capacity_memory_gib() {
    awk '/MemTotal:/ {print int($2/1024/1024)}' /proc/meminfo 2>/dev/null
}

operational_capacity_disk_gib() {
    df -Pk "${FORTIFY_HOME_K8S:-.}" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}'
}

operational_capacity_is_integer() {
    [[ "${1:-}" =~ ^[0-9]+$ ]]
}

operational_capacity_warnings() {
    local memory_gib disk_gib
    memory_gib=$(operational_capacity_memory_gib)
    disk_gib=$(operational_capacity_disk_gib)
    if ! operational_capacity_is_integer "$memory_gib"; then
        printf '%s\n' "memory unknown; recommended minimum is ${FORTIFY_RECOMMENDED_MEMORY_GIB} GiB"
    elif [ "$memory_gib" -lt "$FORTIFY_RECOMMENDED_MEMORY_GIB" ]; then
        printf '%s\n' "memory ${memory_gib} GiB is below recommended ${FORTIFY_RECOMMENDED_MEMORY_GIB} GiB"
    fi
    if ! operational_capacity_is_integer "$disk_gib"; then
        printf '%s\n' "free disk unknown; recommended minimum is ${FORTIFY_RECOMMENDED_DISK_GIB} GiB"
    elif [ "$disk_gib" -lt "$FORTIFY_RECOMMENDED_DISK_GIB" ]; then
        printf '%s\n' "free disk ${disk_gib} GiB is below recommended ${FORTIFY_RECOMMENDED_DISK_GIB} GiB"
    fi
}


operational_render_guide() {
    local topic="${1:-}" file
    case "$topic" in
        deployment) file=deployment-and-lifecycle.md ;;
        networking) file=networking-and-tls.md ;;
        troubleshooting) file=troubleshooting.md ;;
        secrets) file=secrets-and-licenses.md ;;
        recovery) file=backup-and-recovery.md ;;
        versions) file=versions-and-compatibility.md ;;
        diagnostics) file=diagnostics.md ;;
        first-scan) file=first-scan.md ;;
        *) printf 'Unknown operational guide: %s\n' "$topic" >&2; return 2 ;;
    esac
    file="${FORTIFY_HOME_K8S:?FORTIFY_HOME_K8S is required}/docs/operations/$file"
    [ -r "$file" ] || { printf '%s\n' 'The requested operational guide is unavailable.' >&2; return 1; }
    sed 's/^/  /' "$file"
}

operational_notice() {
    printf '%s\n' \
        'LAB / DEMO USE ONLY' \
        'This repository deployment is for evaluation, demonstration, and training.' \
        'It is not a production architecture. Do not use production credentials, source code, customer data, or scan results.'
}

_operational_kubectl() {
    # Intentional word splitting permits the default "microk8s kubectl" command.
    # Callers pass only constants controlled by this module.
    # shellcheck disable=SC2086
    timeout "$FORTIFY_OPERATION_TIMEOUT" $FORTIFY_OPERATION_KUBECTL "$@"
}

operational_cluster_available() {
    command -v timeout >/dev/null 2>&1 || return 1
    # Never wait for MicroK8s startup; this is a bounded, read-only probe.
    _operational_kubectl version --request-timeout="${FORTIFY_OPERATION_TIMEOUT}s" >/dev/null 2>&1
}

operational_print_urls() {
    local domain="${DOMAIN:-fortifydemo.com}"
    printf '%s\n' \
        'Lab URLs (client DNS/hosts must resolve these names to the lab node):' \
        "  SSC:        https://ssc.${domain}" \
        "  SAST:       https://sast.${domain}" \
        "  DAST:       https://dast.${domain}" \
        "  LIM:        https://lim.${domain}" \
        "  Dashboard:  https://dashboard.${domain}" \
        'TLS is issued by the lab-local CA. Import only that CA on dedicated lab clients.'
}

_operational_lab_hosts() {
    local domain="${DOMAIN:-fortifydemo.com}"
    printf '%s\n' \
        "SSC|${SSC:-ssc.${domain}}|${SSC_URL:-https://ssc.${domain}}" \
        "SAST|${SAST:-sast.${domain}}|${SAST_URL:-https://sast.${domain}}" \
        "DAST|${DAST:-dast.${domain}}|${SCDAST_URL:-https://dast.${domain}}" \
        "LIM|${LIM:-lim.${domain}}|${LIM_URL:-https://lim.${domain}}" \
        "Dashboard|${DASHBOARD:-dashboard.${domain}}|${DASHBOARD_URL:-https://dashboard.${domain}}"
}

operational_doctor_hosts_resolution() {
    local label host url resolved state
    printf '%s\n' 'Hosts resolution (first IPv4 answer only):'
    while IFS='|' read -r label host url; do
        resolved=$(getent ahostsv4 "$host" 2>/dev/null | awk 'NR==1 {print $1}')
        if [ -z "$resolved" ]; then
            state=missing
            resolved="-"
        elif printf '%s\n' "$resolved" | grep -Eq '^(127\.|0\.0\.0\.0$)'; then
            state=loopback
        else
            state=resolved
        fi
        printf '  %-10s %-34s %-9s %s\n' "$label" "$host" "$state" "$resolved"
    done <<EOF
$(_operational_lab_hosts)
EOF
}

operational_doctor_coredns_drift() {
    local corefile ready desired observed_hosts=0 expected_hosts=0 label host url state
    printf '%s\n' 'CoreDNS hosts override:'
    if ! operational_cluster_available; then
        printf '%s\n' '  unavailable: cluster is not answering the bounded read-only probe'
        return 0
    fi
    ready=$(_operational_kubectl -n kube-system get deployment coredns \
        -o 'jsonpath={.status.readyReplicas}' 2>/dev/null || true)
    desired=$(_operational_kubectl -n kube-system get deployment coredns \
        -o 'jsonpath={.spec.replicas}' 2>/dev/null || true)
    printf '  deployment: %s/%s ready\n' "${ready:-0}" "${desired:-unknown}"
    corefile=$(_operational_kubectl -n kube-system get configmap coredns \
        -o 'jsonpath={.data.Corefile}' 2>/dev/null || true)
    if [ -z "$corefile" ]; then
        printf '%s\n' '  drift: unknown (CoreDNS configuration was not readable)'
        return 0
    fi
    while IFS='|' read -r label host url; do
        expected_hosts=$((expected_hosts + 1))
        if printf '%s\n' "$corefile" | grep -Fq "$host"; then
            observed_hosts=$((observed_hosts + 1))
        fi
    done <<EOF
$(_operational_lab_hosts)
EOF
    if printf '%s\n' "$corefile" | grep -Fq 'hosts {' && [ "$observed_hosts" -eq "$expected_hosts" ]; then
        state=matches
    else
        state=drift
    fi
    printf '  drift: %s (%s/%s expected lab hostnames present; Corefile contents not displayed)\n' \
        "$state" "$observed_hosts" "$expected_hosts"
}

operational_doctor_ingress() {
    printf '%s\n' 'Ingress controller and classes:'
    if ! operational_cluster_available; then
        printf '%s\n' '  unavailable: cluster is not answering the bounded read-only probe'
        return 0
    fi
    printf '%s\n' '  ingress classes:'
    _operational_kubectl get ingressclass \
        -o 'custom-columns=NAME:.metadata.name,CONTROLLER:.spec.controller' 2>/dev/null |
        sed 's/^/    /' || printf '%s\n' '    none readable'
    printf '%s\n' '  lab ingresses:'
    _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get ingress \
        -o 'custom-columns=NAME:.metadata.name,CLASS:.spec.ingressClassName,HOSTS:.spec.rules[*].host' 2>/dev/null |
        sed 's/^/    /' || printf '%s\n' '    none readable'
}

_operational_endpoint_count() {
    local service="$1"
    _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get endpoints "$service" \
        -o 'jsonpath={range .subsets[*].addresses[*]}x{"\n"}{end}' 2>/dev/null |
        awk 'END {print NR + 0}'
}

operational_doctor_service_endpoints() {
    local label service count state
    printf '%s\n' 'Service endpoints:'
    if ! operational_cluster_available; then
        printf '%s\n' '  unavailable: cluster is not answering the bounded read-only probe'
        return 0
    fi
    while IFS='|' read -r label service; do
        count=$(_operational_endpoint_count "$service")
        if [ "${count:-0}" -gt 0 ]; then
            state=ready
        else
            state=empty
        fi
        printf '  %-10s %-40s %-6s %s endpoint(s)\n' "$label" "$service" "$state" "${count:-0}"
    done <<'EOF'
SSC|ssc-service
LIM|lim
DAST|sdast-core-scancentral-dast-core-api
EOF
}

_operational_http_status() {
    local url="$1" host status
    command -v curl >/dev/null 2>&1 || { printf '%s\n' unavailable; return 1; }
    host=$(printf '%s\n' "$url" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://([^/:]+).*#\1#')
    status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
        --connect-timeout 2 --max-time "$FORTIFY_OPERATION_HTTP_TIMEOUT" \
        --resolve "$host:443:127.0.0.1" "$url" 2>/dev/null) || {
        printf '%s\n' curl-failed
        return 1
    }
    printf '%s\n' "$status"
}

operational_doctor_http_status() {
    local label host url status state
    printf '%s\n' 'HTTP status-only checks through local ingress:'
    while IFS='|' read -r label host url; do
        status=$(_operational_http_status "$url") || true
        case "$status" in
            2*|3*|401|403) state=reachable ;;
            unavailable|curl-failed|000) state=unreachable ;;
            5*) state=server-error ;;
            *) state=unexpected ;;
        esac
        printf '  %-10s %-34s %-12s HTTP %s\n' "$label" "$host" "$state" "$status"
    done <<EOF
$(_operational_lab_hosts)
EOF
}

operational_doctor_compact_health_summary() {
    local label service count url host status capacity_warnings line any_issue=0
    operational_notice
    printf '\nDoctor summary (read-only, compact, secret-safe):\n'
    capacity_warnings=$(operational_capacity_warnings)
    printf '%s\n' '  host capacity:'
    if [ -n "$capacity_warnings" ]; then
        any_issue=1
        while IFS= read -r line; do
            [ -n "$line" ] && printf '    warning: %s\n' "$line"
        done <<<"$capacity_warnings"
    else
        printf '%s\n' '    meets recommended deployment profile'
    fi

    if operational_cluster_available; then
        printf '%s\n' '  cluster: reachable'
        printf '%s\n' '  workloads:'
        _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get statefulsets,deployments \
            -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas' 2>/dev/null |
            sed 's/^/    /' || {
                printf '%s\n' '    none readable'
                any_issue=1
            }
        printf '%s\n' '  endpoints:'
        while IFS='|' read -r label service; do
            count=$(_operational_endpoint_count "$service")
            [ "${count:-0}" -gt 0 ] || any_issue=1
            printf '    %-10s %s endpoint(s)\n' "$label" "${count:-0}"
        done <<'EOF'
SSC|ssc-service
LIM|lim
DAST|sdast-core-scancentral-dast-core-api
EOF
    else
        printf '%s\n' '  cluster: unavailable'
        any_issue=1
    fi
    printf '%s\n' '  http:'
    while IFS='|' read -r label host url; do
        status=$(_operational_http_status "$url") || true
        case "$status" in
            2*|3*|401|403) ;;
            *) any_issue=1 ;;
        esac
        printf '    %-10s HTTP %s\n' "$label" "$status"
    done <<EOF
$(_operational_lab_hosts)
EOF
    if [ "$any_issue" -eq 0 ]; then
        printf '%s\n' '  result: no obvious read-only diagnostic issues detected'
    else
        printf '%s\n' '  result: investigate unavailable, empty, drifted, or failing checks above'
    fi
}

operational_environment_overview() {
    local memory_gib disk_gib certificate capacity_warnings line
    operational_notice
    printf '\nNamespace: %s\n' "$FORTIFY_OPERATION_NAMESPACE"
    operational_print_urls
    memory_gib=$(operational_capacity_memory_gib)
    disk_gib=$(operational_capacity_disk_gib)
    printf '\nHost capacity: %s GiB memory; %s GiB free disk\n' "${memory_gib:-unknown}" "${disk_gib:-unknown}"
    capacity_warnings=$(operational_capacity_warnings)
    if [ -n "$capacity_warnings" ]; then
        printf '%s\n' 'Host capacity warning:'
        while IFS= read -r line; do
            [ -n "$line" ] && printf '  %s\n' "$line"
        done <<<"$capacity_warnings"
    fi
    certificate="${FORTIFY_HOME_K8S:-.}/certs/tls.crt"
    if command -v openssl >/dev/null 2>&1 && [ -r "$certificate" ]; then
        printf 'Lab TLS certificate: '
        openssl x509 -in "$certificate" -noout -enddate 2>/dev/null || printf '%s\n' 'unreadable metadata'
    else
        printf '%s\n' 'Lab TLS certificate: not generated or metadata unavailable'
    fi
    if ! operational_cluster_available; then
        printf '\nCluster status: unavailable or MicroK8s is offline.\n'
        printf '%s\n' 'Configuration help and troubleshooting remain available offline.'
        return 0
    fi
    printf '\nCluster status: answering (read-only summary)\n'
    _operational_kubectl get nodes \
        -o 'custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,KUBELET:.status.nodeInfo.kubeletVersion' 2>/dev/null || true
    printf '\nManaged workloads:\n'
    _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get statefulsets,deployments \
        -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas' 2>/dev/null || \
        printf '%s\n' '  No readable managed workloads found.'
    printf '\nStorage claims:\n'
    _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get pvc \
        -o 'custom-columns=NAME:.metadata.name,STATUS:.status.phase,CAPACITY:.status.capacity.storage' 2>/dev/null || \
        printf '%s\n' '  No readable persistent-volume claims found.'
}

operational_deployment_plan() {
    operational_notice
    printf '%s\n' \
        '' \
        'Deployment plan (dependency order):' \
        '  1. Host prerequisites and MicroK8s' \
        '  2. Lab TLS certificates' \
        '  3. Kubernetes Dashboard' \
        '  4. Kubernetes Secrets (values are never displayed)' \
        '  5. MySQL and PostgreSQL' \
        '  6. SSC and LIM' \
        '  7. ScanCentral SAST' \
        '  8. ScanCentral DAST Core' \
        '  9. ScanCentral DAST scanner' \
        ' 10. Client DNS/TLS trust and first-scan checks' \
        '' \
        'Preview only: this function does not install, upgrade, restart, or delete anything.'
}

_operational_resource_present() {
    local kind="$1" name="$2"
    operational_cluster_available &&
        _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get "$kind" "$name" -o name >/dev/null 2>&1
}

operational_unfinished_summary() {
    local item kind name found_incomplete=0 next_item=""
    operational_notice
    if ! operational_cluster_available; then
        printf '\nProgress unavailable while MicroK8s is offline. No state was changed.\n'
        return 0
    fi
    printf '\nDeployment progress (resource presence, not application health):\n'
    while IFS='|' read -r item kind name; do
        if _operational_resource_present "$kind" "$name"; then
            printf '  [present] %s\n' "$item"
        else
            printf '  [missing] %s\n' "$item"
            [ -n "$next_item" ] || next_item="$item"
            found_incomplete=1
        fi
    done <<'EOF'
MySQL|statefulset|mysql
PostgreSQL|statefulset|postgresql
SSC|statefulset|ssc-webapp
LIM|statefulset|lim
ScanCentral SAST controller|statefulset|scancentral-sast-controller
DAST Core API|statefulset|sdast-core-scancentral-dast-core-api
DAST scanner|statefulset|sdast-scanner-scancentral-dast-scanner
EOF
    if _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get secret fortify-secrets \
        -o 'jsonpath={.metadata.annotations.fortify\.dev/ssc-controller-token-configured}' 2>/dev/null \
        | grep -qx true; then
        printf '%s\n' '  [configured] SSC ControllerToken reference'
    else
        printf '%s\n' '  [required] Configure the SSC ControllerToken for ScanCentral SAST'
        [ -n "$next_item" ] || next_item="SSC ControllerToken configuration"
        found_incomplete=1
    fi
    if _operational_kubectl -n kubernetes-dashboard get service kubernetes-dashboard-kong-proxy \
        -o name >/dev/null 2>&1 || _operational_kubectl -n kube-system get service kubernetes-dashboard \
        -o name >/dev/null 2>&1; then
        printf '%s\n' '  [present] Kubernetes Dashboard service'
    else
        printf '%s\n' '  [missing] Kubernetes Dashboard service'
        [ -n "$next_item" ] || next_item="Kubernetes Dashboard"
        found_incomplete=1
    fi
    printf '%s\n' \
        '  [operator check] LIM DAST license and Default pool' \
        '  [operator check] Client DNS and lab CA trust' \
        '  [operator check] End-to-end synthetic SAST/DAST scan'
    if [ "$found_incomplete" -eq 0 ]; then
        printf '%s\n' 'All detectable resources are present; operator checks and application health still determine readiness.'
    else
        printf 'Next dependency to investigate: %s\n' "$next_item"
        printf '%s\n' 'Presence alone does not prove readiness; use the authenticated health checks before continuing.'
    fi
}

operational_troubleshooting_topic() {
    local topic="${1:-index}"
    case "$topic" in
        failed-deploy) printf '%s\n' 'Failed deployment: find the first failed dependency, correct it, then retry the same operation. Completed steps are safe to detect again.' ;;
        pending-pods) printf '%s\n' 'Pending pods: inspect PVC binding, node capacity, scheduling status, and image-pull state. Do not delete persistent claims as a first response.' ;;
        restarting-pods) printf '%s\n' 'Restarting pods: check readiness state and recent termination reason. Preserve databases and SSC encryption material; collect sanitized diagnostics.' ;;
        url) printf '%s\n' 'URL unreachable: verify client DNS/hosts, ingress readiness, node reachability, and the configured DOMAIN.' ;;
        tls) printf '%s\n' 'TLS warning: confirm the hostname matches the lab certificate and import the lab CA on the dedicated client. Do not disable certificate verification.' ;;
        database) printf '%s\n' 'Database issue: verify the StatefulSet and PVC first, then use the authenticated health probe. Never print database credentials or query output.' ;;
        ssc) printf '%s\n' 'SSC issue: verify MySQL, SSC workload readiness, ingress, and the application endpoint in that order.' ;;
        sast) printf '%s\n' 'SAST issue: verify SSC health and controller-token configuration, then controller/worker readiness. Never paste tokens into logs or diagnostics.' ;;
        dast) printf '%s\n' 'DAST issue: verify PostgreSQL, SSC, LIM license/pool configuration, DAST Core, then scanner registration.' ;;
        dashboard) printf '%s\n' 'Dashboard issue: verify its namespace, service, ingress, client DNS, and TLS trust. Generate only short-lived access tokens and never store them.' ;;
        license) printf '%s\n' 'License issue: verify only that the configured license is readable and non-empty. Never print its path or contents; licensing terms still apply.' ;;
        registry) printf '%s\n' 'Registry issue: verify entitlement and image-pull Secret presence. Rotate exposed credentials outside this wizard; never display or bundle them.' ;;
        index) printf '%s\n' 'Topics: failed-deploy, pending-pods, restarting-pods, url, tls, database, ssc, sast, dast, dashboard, license, registry' ;;
        *) printf 'Unknown troubleshooting topic: %s\n' "$topic" >&2; return 2 ;;
    esac
}

operational_lifecycle_help() {
    printf '%s\n' \
        'Start/upgrade: apply configuration and verify dependencies.' \
        'Stop: scale application workloads down; retain persistent data.' \
        'Restart: stop then start; it is not a repair for corrupted data.' \
        'Repair/retry: rerun an idempotent failed step after fixing its dependency.' \
        'Uninstall: remove application resources; retention depends on the operation.' \
        'Delete data: separately confirmed destruction of persistent claims; not implied by stop or uninstall.'
}

operational_secret_help() {
    printf '%s\n' \
        'Secrets and licenses: report presence/absence only.' \
        'Never display, log, commit, or bundle passwords, tokens, license contents, registry credentials, TLS private keys, or SSC secret.key.' \
        'Do not rotate SSC secret.key or trust roots as incidental troubleshooting.'
}

operational_version_help() {
    printf '%s\n' \
        'Product, Helm chart, and container-image versions are different identifiers.' \
        'Treat .env.example as the tested lab profile; local overrides are configuration drift.' \
        'A running pod does not prove cross-component compatibility. Review release notes before upgrades.' \
        'This profile is lab-tested only and makes no production-support claim.'
}

operational_version_overview() {
    local variable expected configured state
    operational_version_help
    printf '\nConfigured tested-profile identifiers:\n'
    for variable in \
        FORTIFY_SSC_CHART_VERSION FORTIFY_SSC_IMAGE_TAG \
        FORTIFY_SCSAST_CHART_VERSION FORTIFY_SCSAST_CTRL_IMAGE_TAG FORTIFY_SCSAST_WORKER_IMAGE_TAG \
        FORTIFY_SCDAST_CHART_VERSION FORTIFY_LIM_CHART_VERSION \
        FORTIFY_MYSQL_CHART_VERSION FORTIFY_MYSQL_IMAGE_TAG \
        FORTIFY_POSTGRES_CHART_VERSION FORTIFY_POSTGRES_IMAGE_TAG; do
        configured="${!variable:-}"
        expected=$(sed -n -E "s/^[[:space:]]*export[[:space:]]+$variable=\"([^\"]*)\".*/\\1/p" \
            "${FORTIFY_HOME_K8S:-.}/.env.example" 2>/dev/null | head -n 1)
        if [ -z "$configured" ]; then
            state=UNSET
        elif [ -n "$expected" ] && [ "$configured" != "$expected" ]; then
            state=DRIFT
        elif [ -n "$expected" ]; then
            state=MATCH
        else
            state=UNVERIFIED
        fi
        printf '  %-38s %-12s %s\n' "$variable" "$state" "${configured:-<unset>}"
    done
    if operational_cluster_available; then
        printf '\nRunning Kubernetes version:\n'
        _operational_kubectl version -o yaml 2>/dev/null \
            | awk '/gitVersion:/ {print "  " $0}' | head -n 2 || true
        printf 'Running workload images (observed, not compatibility proof):\n'
        _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get statefulsets,deployments \
            -o 'jsonpath={range .items[*]}{.metadata.name}{"|"}{range .spec.template.spec.containers[*]}{.image}{","}{end}{"\n"}{end}' 2>/dev/null \
            | sed 's/^/  /' || true
    fi
}

_operational_sanitize_stream() {
    sed -E \
        -e 's#([A-Za-z0-9_]*(PASS(WORD)?|TOKEN|SECRET|LICENSE|CREDENTIAL|PRIVATE_KEY)[A-Za-z0-9_]*)([=:])[[:space:]]*[^[:space:]]+#\1\4[REDACTED]#Ig' \
        -e 's#(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+/=-]+#\1 [REDACTED]#Ig' \
        -e 's#(/home|/root|/Users)/[^[:space:]]+#[LOCAL_PATH]#g'
}

_operational_wizard_log_excerpt() {
    if ! declare -F fortify_wizard_log_view >/dev/null 2>&1 && [ -n "${FORTIFY_HOME_K8S:-}" ] && [ -r "$FORTIFY_HOME_K8S/scripts/lib/wizard-logging.sh" ]; then
        # shellcheck source=wizard-logging.sh
        source "$FORTIFY_HOME_K8S/scripts/lib/wizard-logging.sh"
    fi
    if declare -F fortify_wizard_log_view >/dev/null 2>&1; then
        fortify_wizard_log_view "${FORTIFY_OPERATION_WIZARD_LOG_LINES:-80}" 2>/dev/null || \
            printf '%s\n' 'Wizard log excerpt unavailable: log file could not be read.'
    else
        printf '%s\n' 'Wizard log excerpt unavailable: logging helpers were not loaded.'
    fi
}

operational_create_diagnostics_bundle() {
    local output_dir="${1:-.}" stamp work bundle archive_status
    [ -d "$output_dir" ] && [ -w "$output_dir" ] || {
        printf '%s\n' 'Diagnostics output directory must already exist and be writable.' >&2
        return 1
    }
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    work=$(mktemp -d "${TMPDIR:-/tmp}/fortify-lab-diagnostics.XXXXXX") || return 1
    bundle="$output_dir/fortify-lab-diagnostics-$stamp.tar.gz"
    {
        operational_notice
        printf 'Created UTC: %s\n' "$stamp"
        printf '%s\n' 'Included: dependency plan, compact cluster status, describe-style Kubernetes summaries, recent events, doctor checks, and a bounded sanitized wizard log excerpt when available.'
        printf '%s\n' 'Excluded: Kubernetes Secret/ConfigMap data, pod/application logs, environment variables, command arguments, tokens, license contents, registry credentials, TLS private keys, database exports, and local configuration paths.'
        printf '%s\n' 'Review every file before sharing; sanitization reduces risk but cannot prove arbitrary context is safe.'
    } >"$work/README.txt"

    operational_deployment_plan >"$work/deployment-plan.txt"
    operational_doctor_compact_health_summary | _operational_sanitize_stream >"$work/doctor-summary.txt"
    {
        operational_doctor_hosts_resolution
        operational_doctor_coredns_drift
        operational_doctor_ingress
        operational_doctor_service_endpoints
        operational_doctor_http_status
    } | _operational_sanitize_stream >"$work/network-diagnostics.txt"
    _operational_wizard_log_excerpt | _operational_sanitize_stream >"$work/wizard-log-excerpt.txt"
    if operational_cluster_available; then
        {
            printf '%s\n' 'NODES'
            _operational_kubectl get nodes -o 'custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,KUBELET:.status.nodeInfo.kubeletVersion' 2>&1 || true
            printf '%s\n' 'WORKLOADS'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get statefulsets,deployments -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas' 2>&1 || true
            printf '%s\n' 'PODS'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get pods -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount' 2>&1 || true
            printf '%s\n' 'SERVICES'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get services -o 'custom-columns=NAME:.metadata.name,TYPE:.spec.type,PORTS:.spec.ports[*].port' 2>&1 || true
            printf '%s\n' 'ENDPOINTS'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get endpoints -o 'custom-columns=NAME:.metadata.name,ENDPOINTS:.subsets[*].addresses[*].ip,PORTS:.subsets[*].ports[*].port' 2>&1 || true
            printf '%s\n' 'STORAGE'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get pvc -o 'custom-columns=NAME:.metadata.name,STATUS:.status.phase,CAPACITY:.status.capacity.storage' 2>&1 || true
            printf '%s\n' 'INGRESS'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get ingress -o 'custom-columns=NAME:.metadata.name,CLASS:.spec.ingressClassName,HOSTS:.spec.rules[*].host' 2>&1 || true
            printf '%s\n' 'RECENT EVENTS'
            _operational_kubectl -n "$FORTIFY_OPERATION_NAMESPACE" get events --sort-by='.lastTimestamp' 2>&1 | tail -20 || true
        } | _operational_sanitize_stream >"$work/kubernetes-evidence.txt"
    else
        printf '%s\n' 'MicroK8s was unavailable; Kubernetes evidence was skipped after a bounded read-only probe.' >"$work/kubernetes-evidence.txt"
    fi
    tar -C "$work" -czf "$bundle" README.txt deployment-plan.txt doctor-summary.txt network-diagnostics.txt kubernetes-evidence.txt wizard-log-excerpt.txt
    archive_status=$?
    rm -rf -- "$work"
    [ "$archive_status" -eq 0 ] || return "$archive_status"
    printf '%s\n' "$bundle"
}
