#!/bin/bash
# start_wizard.sh — Fortify Lab management wizard
#
# Interactive menu for deploying, configuring, and operating the
# Fortify Helm-based lab. Run as your normal user (not root). The
# wizard sudo's only commands that genuinely need it (apt, snap).
# Cluster ops use plain kubectl/helm — no sudo needed when you're
# in the microk8s group.

set -o pipefail


# ============================================================
# Locate FORTIFY_HOME_K8S, source .env
# ============================================================

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export FORTIFY_HOME_K8S
fi

ENV_FILE="$FORTIFY_HOME_K8S/.env"
ENV_EXAMPLE="$FORTIFY_HOME_K8S/.env.example"
ENV_BACKUP_DIR="$FORTIFY_HOME_K8S/.env.backups"


# ============================================================
# Visual helpers (respect NO_COLOR)
# ============================================================

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD="$(tput bold 2>/dev/null || true)"
    DIM="$(tput dim 2>/dev/null || true)"
    RED="$(tput setaf 1 2>/dev/null || true)"
    GREEN="$(tput setaf 2 2>/dev/null || true)"
    YELLOW="$(tput setaf 3 2>/dev/null || true)"
    BLUE="$(tput setaf 4 2>/dev/null || true)"
    RESET="$(tput sgr0 2>/dev/null || true)"
else
    BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
fi

OK_MARK="${GREEN}✓${RESET}"
WARN_MARK="${YELLOW}⚠${RESET}"
FAIL_MARK="${RED}✗${RESET}"
INFO_MARK="${BLUE}ℹ${RESET}"
FORTIFY_RECOMMENDED_MEMORY_GIB="${FORTIFY_RECOMMENDED_MEMORY_GIB:-16}"
FORTIFY_RECOMMENDED_DISK_GIB="${FORTIFY_RECOMMENDED_DISK_GIB:-50}"
FORTIFY_RECOMMENDED_FCLI_VERSION="${FORTIFY_RECOMMENDED_FCLI_VERSION:-3.23.3}"
FORTIFY_FCLI_INSTALL_DIR="${FORTIFY_FCLI_INSTALL_DIR:-$HOME/fortify/tools/bin}"

hr()       { printf '%s\n' "────────────────────────────────────────────────────────────"; }
title()    { clear; printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; hr; }
section()  { printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; }
press_any(){ printf '\n'; read -rp "Press Enter to continue... " _; }
ask()      { local _v="$1"; shift; read -rp "$* " "$_v"; }
confirm()  { local r; read -rp "$1 [y/N] " r; [[ "$r" =~ ^[Yy]$ ]]; }
error()    { printf '%s %s\n' "$FAIL_MARK" "$*" >&2; }
note()     { printf '%s %s\n' "$INFO_MARK" "$*"; }

# shellcheck source=scripts/lib/help.sh
source "$FORTIFY_HOME_K8S/scripts/lib/help.sh"
# shellcheck source=scripts/lib/lab-disclaimer.sh
source "$FORTIFY_HOME_K8S/scripts/lib/lab-disclaimer.sh"
# shellcheck source=scripts/lib/operational-help.sh
source "$FORTIFY_HOME_K8S/scripts/lib/operational-help.sh"
# shellcheck source=scripts/lib/flight-plans.sh
source "$FORTIFY_HOME_K8S/scripts/lib/flight-plans.sh"
# shellcheck source=scripts/lib/release-overlays.sh
source "$FORTIFY_HOME_K8S/scripts/lib/release-overlays.sh"
# shellcheck source=scripts/lib/registry-credentials.sh
source "$FORTIFY_HOME_K8S/scripts/lib/registry-credentials.sh"
# shellcheck source=scripts/lib/tls.sh
source "$FORTIFY_HOME_K8S/scripts/lib/tls.sh"
# shellcheck source=scripts/lib/wizard-logging.sh
source "$FORTIFY_HOME_K8S/scripts/lib/wizard-logging.sh"
# shellcheck source=scripts/lib/coredns-lab-hosts.sh
source "$FORTIFY_HOME_K8S/scripts/lib/coredns-lab-hosts.sh"


# ============================================================
# Cluster CLI detection (microk8s vs upstream)
# ============================================================

if command -v microk8s &>/dev/null; then
    KUBECTL="microk8s kubectl"
    HELM="microk8s helm"
elif command -v kubectl &>/dev/null; then
    KUBECTL="kubectl"
    HELM="helm"
else
    KUBECTL=""
    HELM=""
fi
[ -n "$KUBECTL" ] && FORTIFY_OPERATION_KUBECTL="$KUBECTL"

# ============================================================
# Wizard modules
# ============================================================

source_wizard_module() {
    local module="$1"
    # shellcheck source=/dev/null
    source "$FORTIFY_HOME_K8S/scripts/wizard/$module"
}

source_wizard_module env.sh
source_wizard_module app-registry.sh
source_wizard_module operations.sh
source_wizard_module guided.sh
source_wizard_module runbooks.sh
source_wizard_module setup.sh
source_wizard_module menu.sh

# ============================================================
# Entry
# ============================================================

usage() {
    cat <<EOF
Fortify Lab management wizard.

Usage:
  ./start_wizard.sh                  Launch the interactive menu.
  ./start_wizard.sh --accept-lab-use Explicitly acknowledge lab-only use for automation.
  ./start_wizard.sh doctor           Run a read-only health summary and exit.
  ./start_wizard.sh config-diagnostics
                                      Inspect .env host/URL wiring without printing secrets.
  ./start_wizard.sh apply-flight-plan <plan-id> [--yes]
                                      Stage a Flight Plan's component versions into .env
                                      with a backup, without opening the interactive menu.
                                      Without --yes, prints the impact and pending changes
                                      and exits without writing (dry run).
  ./start_wizard.sh -h | --help      Show this message.

Environment overrides:
  FORTIFY_HOME_K8S    Repo root (defaults to the script's directory).
  EDITOR              Editor used by the raw .env editor fallback (defaults to nano).
  NO_COLOR            Disable color output if set to any value.
  WIZARD_NOMAIN       Set to 1 to source this file without entering the menu
                      (for tests / scripting).

Run as your normal user — the wizard sudo's only the commands that genuinely
need root (apt, snap). Avoid 'sudo ./start_wizard.sh': it would create an
mkcert CA owned by root and rotate every cert the lab has issued.
EOF
}

# Allow sourcing the file for testing without entering the main menu.
if [ -z "${WIZARD_NOMAIN:-}" ]; then
    case "${1:-}" in
        -h|--help) usage; exit 0 ;;
        doctor|config-diagnostics|''|--accept-lab-use|apply-flight-plan) ;;
        *) error "Unsupported argument: ${1}"; usage >&2; exit 2 ;;
    esac
    if [ "${1:-}" = apply-flight-plan ]; then
        apply_flight_plan_id="${2:-}"
        apply_flight_plan_yes=0
        case "${3:-}" in
            --yes) apply_flight_plan_yes=1 ;;
            "") ;;
            *) error "Unsupported argument: ${3}"; usage >&2; exit 2 ;;
        esac
        if [ -z "$apply_flight_plan_id" ] || [ "$#" -gt 3 ]; then
            error "Usage: ./start_wizard.sh apply-flight-plan <plan-id> [--yes]"
            exit 2
        fi
        wizard_apply_flight_plan "$apply_flight_plan_id" "$apply_flight_plan_yes"
        exit $?
    fi
    if [ "$#" -gt 1 ]; then
        error "Only one command-line option is supported."
        usage >&2
        exit 2
    fi
    if [ "${1:-}" = doctor ]; then
        wizard_doctor
        exit $?
    fi
    if [ "${1:-}" = config-diagnostics ]; then
        wizard_config_diagnostics
        exit $?
    fi
    fortify_lab_detect_accept_flag "$@"
    first_launch=0
    fortify_lab_is_acknowledged || first_launch=1
    fortify_lab_require_acknowledgement || exit 1
    ensure_active_groups
    bootstrap_env
    fcli_activate
    guided_apply_deployment_profile "${FORTIFY_DEPLOYMENT_PROFILE:-full_lab}"
    if [ "$first_launch" -eq 1 ]; then
        fortifylab_first_time_welcome_menu
    fi
    main_menu
fi
