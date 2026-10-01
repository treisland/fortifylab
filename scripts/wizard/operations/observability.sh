# shellcheck shell=bash
# Module: operations/observability
# Responsibility: Cluster status, Kubernetes resource selection, and pod log viewing/streaming.
# Layer: operation/menu (legacy-compatible extraction)
# Requires: UI helpers, cluster_reachable, status_cluster, KUBECTL, NAMESPACE, APP_LABEL, APP_PODS.
# Exports: cluster_status, live_status, k8s_resource_names, k8s_select_resource, pod/log helpers, stream_logs.
# Side effects: Reads Kubernetes state; log functions temporarily manage INT traps and spawn processes.
# Interactive: yes.
[ -n "${FORTIFY_WIZARD_OBSERVABILITY_LOADED:-}" ] && return 0
FORTIFY_WIZARD_OBSERVABILITY_LOADED=1

cluster_status() {
    title "Cluster status"
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    section "Pods (namespace: $NAMESPACE)"
    $KUBECTL -n "$NAMESPACE" get pods 2>/dev/null
    section "Pods not Ready"
    local issues
    issues=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
        | awk '$3 != "Running" || ($2 ~ /^[0-9]+\/[0-9]+$/ && split($2,a,"/") && a[1] != a[2])')
    if [ -z "$issues" ]; then
        echo "  (none)"
    else
        echo "$issues"
    fi
    press_any
}

# Auto-refreshing dashboard. Uses our existing status helpers + per-app
# rows; trapped Ctrl+C exits cleanly back to the menu.
live_status() {
    local interval="${1:-5}"
    trap 'live_status_running=0' INT
    live_status_running=1

    while [ "$live_status_running" -eq 1 ]; do
        clear
        printf '%sFortify Lab — Live Status%s   refresh %ss   Ctrl+C to exit\n' \
            "$BOLD" "$RESET" "$interval"
        printf '%s%s%s\n' "$DIM" "$(date '+%Y-%m-%d %H:%M:%S')" "$RESET"
        hr

        section "Cluster"
        printf '  %s\n' "$(status_cluster)"

        if cluster_reachable; then
            section "Apps"
            local i pods total ready issues
            for i in "${!APP_LABEL[@]}"; do
                pods=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
                       | awk -v p="${APP_PODS[$i]}" '$1 ~ "^"p {print}')
                if [ -z "$pods" ]; then
                    printf '  %-20s %snot deployed%s\n' "${APP_LABEL[$i]}" "$DIM" "$RESET"
                    continue
                fi
                total=$(echo "$pods" | wc -l)
                ready=$(echo "$pods" | awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}')
                if [ "$ready" -eq "$total" ]; then
                    printf '  %-20s %s%d/%d running%s\n' \
                        "${APP_LABEL[$i]}" "$GREEN" "$ready" "$total" "$RESET"
                else
                    printf '  %-20s %s%d/%d ready%s\n' \
                        "${APP_LABEL[$i]}" "$YELLOW" "$ready" "$total" "$RESET"
                    # Show offenders inline so the user sees why
                    echo "$pods" | awk '$3!="Running" || ($2 ~ /^[0-9]+\/[0-9]+$/ && split($2,a,"/") && a[1]!=a[2]) { printf "    %s%s%s  %s  %s\n", "'"$DIM"'", $1, "'"$RESET"'", $2, $3 }'
                fi
            done

            section "Recent events (last 8)"
            $KUBECTL -n "$NAMESPACE" get events --sort-by='.lastTimestamp' 2>/dev/null \
              | tail -8 \
              | awk 'NR>0 { printf "  %s\n", $0 }'
        fi

        # Sleep responsively so Ctrl+C exits within ~1s.
        local elapsed=0
        while [ "$elapsed" -lt "$interval" ] && [ "$live_status_running" -eq 1 ]; do
            sleep 1
            elapsed=$((elapsed + 1))
        done
    done

    trap - INT
    clear
}

k8s_resource_names() {
    local kind="$1" filter="${2:-}" prefix="${3:-}" name
    [ -n "$KUBECTL" ] || return 1
    while IFS= read -r name; do
        name="${name#*/}"
        [ -n "$name" ] || continue
        [ -z "$prefix" ] || [[ "$name" == "$prefix"* ]] || continue
        [ -z "$filter" ] || [[ "$name" == *"$filter"* ]] || continue
        printf '%s\n' "$name"
    done < <($KUBECTL -n "$NAMESPACE" get "$kind" -o name 2>/dev/null)
}

k8s_select_resource() {
    local kind="$1" prompt="${2:-Select resource}" filter="${3:-}" prefix="${4:-}"
    local resources=() i sel exact
    K8S_SELECTED_RESOURCE_KIND=""
    K8S_SELECTED_RESOURCE_NAME=""

    while true; do
        mapfile -t resources < <(k8s_resource_names "$kind" "$filter" "$prefix")
        printf '\n%s\n' "$prompt"
        if [ -n "$filter" ]; then
            printf '  Filter: %s\n' "$filter"
        fi
        if [ -n "$prefix" ]; then
            printf '  Scope:  %s*\n' "$prefix"
        fi
        if [ ${#resources[@]} -eq 0 ]; then
            note "No ${kind}s matched '${filter:-all}'."
        else
            for i in "${!resources[@]}"; do
                printf '  %2d. %s\n' $((i + 1)) "${resources[$i]}"
            done
        fi
        printf '\n  f. Filter list   x. Enter exact name   b. Back\n'
        ask sel "${kind^} number:"
        case "$sel" in
            [Bb]|"") return 1 ;;
            [Ff])
                ask filter "Filter (substring, blank=all):"
                ;;
            [Xx])
                ask exact "Exact ${kind} name:"
                [ -n "$exact" ] || { error "Name cannot be blank"; continue; }
                K8S_SELECTED_RESOURCE_KIND="$kind"
                K8S_SELECTED_RESOURCE_NAME="$exact"
                return 0
                ;;
            *)
                if [[ "$sel" =~ ^[0-9]+$ ]] && [ "$sel" -ge 1 ] && [ "$sel" -le ${#resources[@]} ]; then
                    K8S_SELECTED_RESOURCE_KIND="$kind"
                    K8S_SELECTED_RESOURCE_NAME="${resources[$((sel-1))]}"
                    return 0
                fi
                error "Invalid selection."
                ;;
        esac
    done
}

pod_has_restarts() {
    local pod="$1"
    $KUBECTL -n "$NAMESPACE" get pod "$pod" \
        -o jsonpath='{range .status.containerStatuses[*]}{.restartCount}{"\\n"}{end}' 2>/dev/null \
        | awk '$1 > 0 { found=1 } END { exit found ? 0 : 1 }'
}

restore_int_trap() {
    local saved_trap="${1:-}"
    if [ -n "$saved_trap" ]; then
        eval "$saved_trap"
    else
        trap - INT
    fi
}

follow_pod_logs_safe() {
    local pod="$1" tail_lines="${2:-100}" pid rc saved_int_trap interrupted=0
    saved_int_trap=$(trap -p INT || true)
    (
        trap - INT
        $KUBECTL -n "$NAMESPACE" logs --all-containers --follow --tail="$tail_lines" --ignore-errors=true "$pod"
    ) &
    pid=$!
    trap 'interrupted=1; kill -INT "$pid" 2>/dev/null; sleep 0.2; kill -TERM "$pid" 2>/dev/null' INT
    wait "$pid"
    rc=$?
    restore_int_trap "$saved_int_trap"
    if [ "$interrupted" -eq 1 ] || [ "$rc" -ge 130 ]; then
        note "Stopped following logs for $pod."
        return 0
    fi
    return "$rc"
}

pod_log_action_menu() {
    local pod="$1" choice previous_label
    while true; do
        previous_label="Previous container logs"
        pod_has_restarts "$pod" || previous_label="Previous container logs (if available)"
        printf '\nPod: %s\n' "$pod"
        printf '  1. Recent logs\n'
        printf '  2. Follow logs\n'
        printf '  3. %s\n' "$previous_label"
        printf '  b. Back\n'
        ask choice "Select:"
        case "$choice" in
            1)
                $KUBECTL -n "$NAMESPACE" logs --all-containers --tail=200 "$pod" || true
                press_any
                return 0
                ;;
            2)
                note "Following logs for $pod. Press Ctrl+C to return to Fortify Lab."
                follow_pod_logs_safe "$pod" 100 || true
                press_any
                return 0
                ;;
            3)
                $KUBECTL -n "$NAMESPACE" logs --all-containers --previous --tail=200 "$pod" || true
                press_any
                return 0
                ;;
            [Bb]|"") return 1 ;;
            *) error "Invalid selection." ;;
        esac
    done
}

logs_menu() {
    title "Pod logs"
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    if k8s_select_resource pod "Select a pod"; then
        pod_log_action_menu "$K8S_SELECTED_RESOURCE_NAME"
    fi
}

logs_for_prefix() {
    local prefix="$1" pods=()
    mapfile -t pods < <(k8s_resource_names pod "" "$prefix")
    case "${#pods[@]}" in
        0)
            note "No pods matching '$prefix' have appeared yet."
            press_any
            ;;
        1)
            pod_log_action_menu "${pods[0]}"
            ;;
        *)
            if k8s_select_resource pod "Select a pod" "" "$prefix"; then
                pod_log_action_menu "$K8S_SELECTED_RESOURCE_NAME"
            else
                note "No pod selected."
                press_any
            fi
            ;;
    esac
}

# Multi-pod log streamer. Tails every pod in $NAMESPACE in parallel,
# tagging each line with a colored [pod-name] prefix. Optional substring
# filter applies to the LINE, not the pod name (use logs_menu for that).
# Ctrl+C kills all backgrounded tails and returns to the menu.
stream_logs() {
    title "Stream logs (all pods)"
    if ! cluster_reachable; then
        error "Cluster not reachable"
        press_any; return
    fi
    local pods=()
    mapfile -t pods < <($KUBECTL -n "$NAMESPACE" get pods -o name 2>/dev/null | sed 's|^pod/||')
    if [ ${#pods[@]} -eq 0 ]; then
        note "No pods in '$NAMESPACE'"
        press_any; return
    fi
    echo
    echo "  ${#pods[@]} pods will be tailed in parallel."
    echo "  Tip: filter to surface the lines you care about (errors, specific words)."
    echo
    ask filter "Line filter (substring, blank for all):"

    local pids=() pod color color_idx short
    # Cycle through 6 ANSI colors so adjacent pods read distinct.
    local colors=(1 2 3 4 5 6)

    # Each pod tail runs in a backgrounded subshell. The parent owns Ctrl+C
    # handling, terminates those subshells, waits for them, and restores the
    # previous interrupt trap before returning to the menu.
    cleanup_streams() {
        local p
        for p in "${pids[@]}"; do
            if command -v pkill >/dev/null 2>&1; then
                pkill -TERM -P "$p" 2>/dev/null || true
            fi
            kill -TERM "$p" 2>/dev/null
        done
        # Brief grace, then verify clean.
        sleep 0.3
        for p in "${pids[@]}"; do
            wait "$p" 2>/dev/null
        done
        pids=()
    }
    local saved_int_trap stream_interrupted=0
    saved_int_trap=$(trap -p INT || true)
    trap 'stream_interrupted=1; cleanup_streams' INT

    echo
    note "Streaming. Ctrl+C to stop."
    echo

    for i in "${!pods[@]}"; do
        pod="${pods[$i]}"
        color_idx="${colors[$((i % ${#colors[@]}))]}"
        if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
            color="$(tput setaf "$color_idx" 2>/dev/null || true)"
        else
            color=""
        fi
        short="$pod"

        if [ -n "$filter" ]; then
            (
              trap - INT TERM
              $KUBECTL -n "$NAMESPACE" logs --follow --all-containers --tail=20 \
                  --ignore-errors=true "$pod" 2>&1 \
              | grep --line-buffered -F -- "$filter" \
              | awk -v c="$color" -v r="$RESET" -v p="$short" \
                  '{ printf "%s[%s]%s %s\n", c, p, r, $0; fflush() }'
            ) &
        else
            (
              trap - INT TERM
              $KUBECTL -n "$NAMESPACE" logs --follow --all-containers --tail=20 \
                  --ignore-errors=true "$pod" 2>&1 \
              | awk -v c="$color" -v r="$RESET" -v p="$short" \
                  '{ printf "%s[%s]%s %s\n", c, p, r, $0; fflush() }'
            ) &
        fi
        pids+=("$!")
    done

    # Block until all backgrounded tails exit OR Ctrl+C trips the trap.
    wait || true
    cleanup_streams
    restore_int_trap "$saved_int_trap"
    if [ "$stream_interrupted" -eq 1 ]; then
        echo
        note "Stopped streaming logs."
    fi
}

