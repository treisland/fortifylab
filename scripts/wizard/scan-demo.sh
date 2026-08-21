#!/usr/bin/env bash
# shellcheck shell=bash
#
# First-scan one-click demo: submits a real ScanCentral SAST scan against a
# configured sample application (default: IWA-Java) and surfaces severity
# counts from SSC, with no manual fcli/SSC setup beyond what the wizard
# already automates (PATH + TLS trust; see fcli_activate).
#
# This is a companion to docs/operations/first-scan.md, not a replacement:
# the manual walkthrough there is deliberately careful/synthetic-input-only
# for teaching the full verification path. This flow is the "just show me a
# real result" fast path once you already understand that path, and it still
# requires pasting an SSC token when asked -- consistent with the rest of the
# wizard, no SSC credential is ever written to .env or disk.
#
# Scan-type shape (Phase 1 of the design): every scan type implements
# scan_type_prereqs_<type>, scan_type_login_<type>, scan_type_sensor_check_<type>,
# scan_type_acquire_<type>, scan_type_package_<type>, scan_type_submit_<type>,
# scan_type_poll_<type>, scan_type_verify_<type>, scan_type_results_<type>,
# scan_type_logout_<type>. scan_demo_run dispatches through that shape by
# name, so adding SCA (Debricked) or DAST later is a new set of functions,
# not a rework of the menu/orchestration below. Only "sast_iwa_java" exists
# today.

FORTIFY_FIRST_SCAN_APP="${FORTIFY_FIRST_SCAN_APP:-IWA-Java}"
FORTIFY_FIRST_SCAN_REPO_URL="${FORTIFY_FIRST_SCAN_REPO_URL:-https://github.com/fortify/IWA-Java}"
FORTIFY_FIRST_SCAN_SSC_SESSION="${FORTIFY_FIRST_SCAN_SSC_SESSION:-fortifylab-first-scan}"
FORTIFY_FIRST_SCAN_POLL_INTERVAL="${FORTIFY_FIRST_SCAN_POLL_INTERVAL:-15}"
FORTIFY_FIRST_SCAN_POLL_TIMEOUT="${FORTIFY_FIRST_SCAN_POLL_TIMEOUT:-1800}"

scan_demo_run_id() {
    date +%Y%m%d%H%M%S
}

# ------------------------------------------------------------------
# sast_iwa_java scan type
# ------------------------------------------------------------------

scan_type_prereqs_sast_iwa_java() {
    local ok=1
    if ! fcli_path >/dev/null 2>&1; then
        error "fcli is not installed. Use Tools and FCLI readiness -> Install or update FCLI."
        ok=0
    fi
    if [ -z "${SSC_URL:-}" ]; then
        error "SSC_URL is not set. Configure it before running the first-scan demo."
        ok=0
    fi
    if [ -z "${FORTIFY_FIRST_SCAN_REPO_URL:-}" ]; then
        error "FORTIFY_FIRST_SCAN_REPO_URL is empty. Set it in .env, or unset the override to use the default."
        ok=0
    fi
    command -v git >/dev/null 2>&1 || { error "git is required to clone $FORTIFY_FIRST_SCAN_APP."; ok=0; }
    [ "$ok" -eq 1 ]
}

scan_type_check_egress_sast_iwa_java() {
    local timeout_cmd=""
    command -v timeout >/dev/null 2>&1 && timeout_cmd="timeout 10"
    if ! $timeout_cmd git ls-remote "$FORTIFY_FIRST_SCAN_REPO_URL" HEAD >/dev/null 2>&1; then
        error "Could not reach $FORTIFY_FIRST_SCAN_REPO_URL. Check network egress from this host."
        note "Isolated labs need a vendored/cached copy of $FORTIFY_FIRST_SCAN_APP instead of a live clone."
        return 1
    fi
}

scan_type_login_sast_iwa_java() {
    local token="$1" fcli_bin
    local -a extra_args=()
    fcli_bin="$(fcli_path)" || return 1
    [ -n "${SCSAST_CTRL_URL:-}" ] && extra_args=(--sc-sast-url "$SCSAST_CTRL_URL")
    "$fcli_bin" ssc session login --url "$SSC_URL" "${extra_args[@]}" \
        --ci-token="$token" --ssc-session="$FORTIFY_FIRST_SCAN_SSC_SESSION"
}

scan_type_sensor_check_sast_iwa_java() {
    local fcli_bin output
    fcli_bin="$(fcli_path)" || return 1
    output="$("$fcli_bin" sc-sast sensor list --ssc-session="$FORTIFY_FIRST_SCAN_SSC_SESSION" 2>&1)" || {
        error "Could not list ScanCentral SAST sensors: $output"
        return 1
    }
    if printf '%s' "$output" | grep -qiE 'no (sensors|entries|results) (found|available)|^\s*$'; then
        error "No ScanCentral SAST sensor is registered. Submitting now would queue forever."
        note "Confirm a worker is deployed and connected before retrying."
        return 1
    fi
}

scan_type_acquire_sast_iwa_java() {
    local workdir="$1"
    scan_type_check_egress_sast_iwa_java || return 1
    git clone --depth 1 "$FORTIFY_FIRST_SCAN_REPO_URL" "$workdir/src" || {
        error "Could not clone $FORTIFY_FIRST_SCAN_APP from $FORTIFY_FIRST_SCAN_REPO_URL."
        return 1
    }
}

scan_type_package_sast_iwa_java() {
    local workdir="$1" fcli_bin
    fcli_bin="$(fcli_path)" || return 1
    "$fcli_bin" sc-sast package --source "$workdir/src" --output "$workdir/$FORTIFY_FIRST_SCAN_APP.zip"
}

scan_type_submit_sast_iwa_java() {
    local workdir="$1" av_name="$2" fcli_bin
    fcli_bin="$(fcli_path)" || return 1
    "$fcli_bin" sc-sast scan start \
        --file="$workdir/$FORTIFY_FIRST_SCAN_APP.zip" \
        --publish-to="$av_name" \
        --ssc-session="$FORTIFY_FIRST_SCAN_SSC_SESSION" \
        --store=first_scan_job
}

# Polls status on an interval and prints progress, rather than a single
# blocking wait-for call, so a multi-minute SAST scan doesn't look frozen.
# Returns 0 only once a terminal state (success or failure) is observed;
# scan_type_verify_sast_iwa_java decides whether that terminal state means
# the scan actually succeeded.
scan_type_poll_sast_iwa_java() {
    local fcli_bin elapsed=0 status
    fcli_bin="$(fcli_path)" || return 1
    while [ "$elapsed" -lt "$FORTIFY_FIRST_SCAN_POLL_TIMEOUT" ]; do
        status="$("$fcli_bin" sc-sast scan status ::first_scan_job::scanId \
            --ssc-session="$FORTIFY_FIRST_SCAN_SSC_SESSION" 2>&1)"
        note "Scan status: $(printf '%s' "$status" | tr '\n' ' ' | head -c 200)"
        if printf '%s' "$status" | grep -qiE 'COMPLETE|FAULTED|FAILED|CANCELED|TIMEOUT'; then
            LAST_SCAN_STATUS="$status"
            return 0
        fi
        sleep "$FORTIFY_FIRST_SCAN_POLL_INTERVAL"
        elapsed=$((elapsed + FORTIFY_FIRST_SCAN_POLL_INTERVAL))
    done
    error "Timed out after ${FORTIFY_FIRST_SCAN_POLL_TIMEOUT}s waiting for the scan to finish."
    return 1
}

# Explicit success check: a terminal state from scan_type_poll_sast_iwa_java
# is not automatically success. FAULTED/FAILED/CANCELED/TIMEOUT must be
# reported as failure, not silently treated as "done."
scan_type_verify_sast_iwa_java() {
    if printf '%s' "${LAST_SCAN_STATUS:-}" | grep -qiE 'FAULTED|FAILED|CANCELED|TIMEOUT'; then
        error "Scan did not complete successfully: ${LAST_SCAN_STATUS}"
        return 1
    fi
    if ! printf '%s' "${LAST_SCAN_STATUS:-}" | grep -qi 'COMPLETE'; then
        error "Could not confirm scan completion from status output: ${LAST_SCAN_STATUS}"
        return 1
    fi
}

scan_type_results_sast_iwa_java() {
    local av_name="$1" fcli_bin
    fcli_bin="$(fcli_path)" || return 1
    section "Severity summary for $av_name"
    "$fcli_bin" ssc issue count --av="$av_name" --by=folder --ssc-session="$FORTIFY_FIRST_SCAN_SSC_SESSION"
}

scan_type_logout_sast_iwa_java() {
    local fcli_bin
    fcli_bin="$(fcli_path)" || return 0
    "$fcli_bin" ssc session logout --ssc-session="$FORTIFY_FIRST_SCAN_SSC_SESSION" >/dev/null 2>&1 || true
}

# ------------------------------------------------------------------
# Shared orchestration
# ------------------------------------------------------------------

scan_demo_menu() {
    title "First-scan one-click demo"
    cat <<EOF

  Runs a real ScanCentral SAST scan against $FORTIFY_FIRST_SCAN_APP and shows
  severity counts from SSC. Requires an SSC token with permission to create
  application versions and submit scans -- pasted once below, never written
  to .env or disk.

EOF
    scan_type_prereqs_sast_iwa_java || { press_any; return 1; }
    confirm "Continue?" || return 0

    local token workdir av_name rc=0
    read -rsp "Paste SSC token (input hidden; empty cancels): " token
    echo
    [ -z "$token" ] && { note "Cancelled."; press_any; return 0; }

    workdir="$(mktemp -d)" || { error "Could not create a scratch directory."; press_any; return 1; }
    av_name="${FORTIFY_FIRST_SCAN_APP}:demo-$(scan_demo_run_id)"

    trap 'scan_type_logout_sast_iwa_java; rm -rf "$workdir"' RETURN

    note "Logging in to SSC..."
    scan_type_login_sast_iwa_java "$token" || { press_any; return 1; }
    token=""

    note "Checking for an available ScanCentral SAST sensor..."
    scan_type_sensor_check_sast_iwa_java || { rc=1; }

    if [ "$rc" -eq 0 ]; then
        note "Cloning $FORTIFY_FIRST_SCAN_APP..."
        scan_type_acquire_sast_iwa_java "$workdir" || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
        note "Packaging source..."
        scan_type_package_sast_iwa_java "$workdir" || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
        note "Submitting scan to $av_name..."
        scan_type_submit_sast_iwa_java "$workdir" "$av_name" || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
        scan_type_poll_sast_iwa_java || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
        scan_type_verify_sast_iwa_java || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
        scan_type_results_sast_iwa_java "$av_name"
        note "Full detail: open $av_name in the SSC web UI, or run 'fcli ssc issue list --av=\"$av_name\"'."
    fi

    press_any
    return "$rc"
}
