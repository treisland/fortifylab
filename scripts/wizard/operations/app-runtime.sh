# shellcheck shell=bash
# Module: operations/app-runtime
# Responsibility: Application status lookup and component script execution.
# Requires: application registry, SCRIPT_DIR, UI helpers
# Exports: app_status, run_app_scripts
# Side effects: Reads Kubernetes state and executes registered component scripts.
# Interactive: yes where exported menu functions are present.

if [[ -n "${FORTIFYLAB_WIZARD_OPERATIONS_APP_RUNTIME_LOADED:-}" ]]; then
  return 0
fi
readonly FORTIFYLAB_WIZARD_OPERATIONS_APP_RUNTIME_LOADED=1

# ============================================================

# Aggregate status for one app (e.g. "3/3 ready" or "0/0 not deployed").
app_status() {
    local prefix="$1" total ready
    local pods
    pods=$($KUBECTL -n "$NAMESPACE" get pods --no-headers 2>/dev/null \
           | awk -v p="$prefix" '$1 ~ "^"p {print}')
    if [ -z "$pods" ]; then
        printf '%snot deployed%s' "$DIM" "$RESET"
        return
    fi
    total=$(echo "$pods" | wc -l)
    ready=$(echo "$pods" | awk '$3=="Running" {n=split($2,a,"/"); if (a[1]==a[2]) c++} END{print c+0}')
    if [ "$ready" -eq "$total" ]; then
        printf '%s%d/%d running%s' "$GREEN" "$ready" "$total" "$RESET"
    else
        printf '%s%d/%d ready%s' "$YELLOW" "$ready" "$total" "$RESET"
    fi
}

# Run a (possibly multi-) script field from APP_START/STOP/DESTROY.
run_app_scripts() {
    local field="$1" script
    for script in $field; do
        if [ ! -f "$FORTIFY_HOME_K8S/$script" ]; then
            error "Missing $script"
            return 1
        fi
        bash "$FORTIFY_HOME_K8S/$script" || return $?
    done
}
