#!/bin/bash
# Idempotent Kubernetes scaling helpers for lab lifecycle operations.

fortify_kubectl() {
    if [ -n "${FORTIFY_OPERATION_KUBECTL:-}" ]; then
        $FORTIFY_OPERATION_KUBECTL "$@"
    else
        microk8s kubectl "$@"
    fi
}

fortify_scale_statefulset_if_exists() {
    local namespace="$1" statefulset="$2" replicas="$3"
    if fortify_kubectl -n "$namespace" get statefulset "$statefulset" >/dev/null 2>&1; then
        fortify_kubectl -n "$namespace" scale statefulset "$statefulset" --replicas="$replicas"
    else
        printf 'statefulset.apps "%s" not found in %s namespace; already stopped.
' "$statefulset" "$namespace"
    fi
}

# The ScanCentral SAST sensor's StatefulSet name has varied across chart
# versions/configs (scancentral-sast-sensor-linux, scancentral-sast-sensor,
# scancentral-sast-worker-linux). Scaling only the "worker-linux" name left
# the sensor running after "stop" on labs deployed with an older/different
# chart that named it something else -- guided.sh's own readiness checks
# already tried all three names; the stop/scale scripts didn't. Single
# source of truth for that name list.
fortify_sast_sensor_statefulset_names() {
    printf '%s\n' scancentral-sast-sensor-linux scancentral-sast-sensor scancentral-sast-worker-linux
}

# Scales every ScanCentral SAST sensor StatefulSet name that actually
# exists (there should only be one deployed at a time, but this doesn't
# assume that), instead of silently no-op'ing when the deployed chart named
# it differently than expected.
fortify_scale_sast_sensor_if_exists() {
    local namespace="$1" replicas="$2" name found=0
    for name in $(fortify_sast_sensor_statefulset_names); do
        if fortify_kubectl -n "$namespace" get statefulset "$name" >/dev/null 2>&1; then
            fortify_kubectl -n "$namespace" scale statefulset "$name" --replicas="$replicas"
            found=1
        fi
    done
    if [ "$found" -eq 0 ]; then
        printf 'No ScanCentral SAST sensor StatefulSet found in %s namespace (checked: %s); already stopped.\n' \
            "$namespace" "$(fortify_sast_sensor_statefulset_names | paste -sd ' ' -)"
    fi
}
