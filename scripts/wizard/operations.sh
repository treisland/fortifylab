#!/bin/bash
# shellcheck shell=bash
#
# Compatibility loader for the Bash operations layer.
#
# Feature implementations live in scripts/wizard/operations/ and
# scripts/wizard/flight-plans/. Keep the order explicit: modules may call
# functions loaded later at runtime, but must not source one another.

[ -n "${FORTIFY_WIZARD_OPERATIONS_LOADED:-}" ] && return 0

source_wizard_operation_module() {
    local relative_path="$1"
    if [[ ! "$relative_path" =~ ^(operations|flight-plans)/[a-z0-9-]+\.sh$ ]]; then
        error "Invalid wizard operation module: $relative_path"
        return 2
    fi

    if [ ! -r "$FORTIFY_HOME_K8S/scripts/wizard/$relative_path" ]; then
        error "Required wizard operation module is missing: $relative_path"
        return 1
    fi

    # shellcheck source=/dev/null
    source "$FORTIFY_HOME_K8S/scripts/wizard/$relative_path"
}

WIZARD_OPERATION_MODULES=(
    # Foundation and application lifecycle.
    operations/status.sh
    operations/cluster-profiles.sh
    operations/app-runtime.sh
    operations/lifecycle.sh
    operations/apps-menu.sh
    operations/license.sh
    operations/certificates.sh
    operations/dashboard-access.sh
    operations/configuration-actions.sh
    # Read-only operations and credential handoff.
    operations/observability.sh
    operations/credentials.sh
    # Environment persistence precedes consumers that stage changes.
    operations/environment-store.sh
    flight-plans/catalog.sh
    flight-plans/staging.sh
    flight-plans/menu.sh
    operations/fcli.sh
    operations/deployment-versions.sh
    operations/environment-editor.sh
    operations/certificates-trust.sh
    # Interactive aggregators load last.
    operations/prerequisites.sh
    operations/advanced-menus.sh
)

for wizard_operation_module in "${WIZARD_OPERATION_MODULES[@]}"; do
    source_wizard_operation_module "$wizard_operation_module" || {
        wizard_operation_status=$?
        unset FORTIFY_WIZARD_OPERATIONS_LOADED
        return "$wizard_operation_status"
    }
done
unset wizard_operation_module
unset wizard_operation_status
FORTIFY_WIZARD_OPERATIONS_LOADED=1
