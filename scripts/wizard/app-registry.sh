#!/usr/bin/env bash
# shellcheck shell=bash

# ============================================================
# App registry — single source of truth for the apps menu
# ============================================================

APP_LABEL=("MySQL" "PostgreSQL" "SSC" "LIM" "ScanCentral SAST" "ScanCentral DAST" "Juice Shop" "WebGoat" "DVWA")
APP_PODS=("mysql"  "postgresql" "ssc-webapp" "lim" "scancentral-sast" "sdast" "sample-juice-shop" "sample-webgoat" "sample-dvwa")
APP_URL_VAR=(""    ""           "SSC_URL"    "LIM_URL" "SCSAST_CTRL_URL" "SCDAST_URL" "JUICE_SHOP_URL" "WEBGOAT_URL" "DVWA_URL")
APP_GUIDED_STEP=("mysql" "postgresql" "ssc" "lim" "sast" "dast" "sample_juice_shop" "sample_webgoat" "sample_dvwa")
APP_SAMPLE=(0 0 0 0 0 0 1 1 1)
APP_START=(
    "apps/mysql/start.sh"
    "apps/postgresql/start.sh"
    "apps/ssc/start.sh"
    "apps/lim/start.sh"
    "apps/scsast/start.sh"
    "apps/scdast/core/start.sh apps/scdast/scanner/start.sh"
    "apps/samples/juice-shop/start.sh"
    "apps/samples/webgoat/start.sh"
    "apps/samples/dvwa/start.sh"
)
APP_STOP=(
    "apps/mysql/stop.sh"
    "apps/postgresql/stop.sh"
    "apps/ssc/stop.sh"
    "apps/lim/stop.sh"
    "apps/scsast/stop.sh"
    "apps/scdast/core/stop.sh apps/scdast/scanner/stop.sh"
    "apps/samples/juice-shop/stop.sh"
    "apps/samples/webgoat/stop.sh"
    "apps/samples/dvwa/stop.sh"
)
APP_DESTROY=(
    "apps/mysql/destroy.sh"
    "apps/postgresql/destroy.sh"
    "apps/ssc/destroy.sh"
    "apps/lim/destroy.sh"
    "apps/scsast/destroy.sh"
    "apps/scdast/core/destroy.sh apps/scdast/scanner/destroy.sh"
    "apps/samples/juice-shop/destroy.sh"
    "apps/samples/webgoat/destroy.sh"
    "apps/samples/dvwa/destroy.sh"
)

app_index_is_sample() {
    [ "${APP_SAMPLE[$1]:-0}" -eq 1 ]
}

app_index_in_full_lifecycle() {
    ! app_index_is_sample "$1"
}

sample_default_url_for_var() {
    local variable="$1" domain="${DOMAIN:-fortifydemo.com}"
    case "$variable" in
        JUICE_SHOP_URL) printf '%s\n' "https://juice-shop.$domain" ;;
        WEBGOAT_URL) printf '%s\n' "https://webgoat.$domain" ;;
        DVWA_URL) printf '%s\n' "https://dvwa.$domain" ;;
        *) return 1 ;;
    esac
}

app_url_for_index() {
    local idx="$1" variable="" value=""
    variable="${APP_URL_VAR[$idx]:-}"
    [ -n "$variable" ] || return 0
    value="${!variable:-}"
    if [ -z "$value" ]; then
        value="$(sample_default_url_for_var "$variable" 2>/dev/null || true)"
    fi
    printf '%s\n' "$value"
}

app_url_display_for_index() {
    local idx="$1" variable="" value=""
    variable="${APP_URL_VAR[$idx]:-}"
    [ -n "$variable" ] || return 0
    value=$(app_url_for_index "$idx")
    [ -n "$value" ] || return 0
    if [[ "$value" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
        printf '<invalid: %s=%s>\n' "$variable" "$value"
    else
        printf '%s\n' "$value"
    fi
}
