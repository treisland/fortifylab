#!/usr/bin/env bash
# shellcheck shell=bash

# ============================================================
# Source .env (creates from .env.example on first run)
# ============================================================

bootstrap_env() {
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            note "Created $ENV_FILE from .env.example."
            note "Use Advanced setup -> Configuration editor to set your domain, passwords, and image versions."
            press_any
        else
            error "Neither .env nor .env.example found in $FORTIFY_HOME_K8S."
            exit 1
        fi
    fi
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    FORTIFY_OPERATION_NAMESPACE="${NAMESPACE:-fortify}"
}
