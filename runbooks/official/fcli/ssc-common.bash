#!/usr/bin/env bash
# Shared helper for local SSC fcli runbooks. Not directly discoverable.

set -euo pipefail

ssc_note() {
  printf '\n[%s] %s\n' "$1" "$2"
}

ssc_resolve_fcli_bin() {
  if [[ -n "${FCLI_BIN:-}" ]]; then
    printf '%s\n' "$FCLI_BIN"
    return 0
  fi
  if [[ -n "${FORTIFY_FCLI_INSTALL_DIR:-}" && -x "${FORTIFY_FCLI_INSTALL_DIR}/fcli" ]]; then
    printf '%s\n' "${FORTIFY_FCLI_INSTALL_DIR}/fcli"
    return 0
  fi
  command -v fcli 2>/dev/null || return 1
}

ssc_require_fcli() {
  FCLI_CMD="$(ssc_resolve_fcli_bin || true)"
  if [[ -z "$FCLI_CMD" ]]; then
    printf 'fcli not found. Install it from the wizard Tools/FCLI readiness screen or set FCLI_BIN.\n' >&2
    exit 127
  fi
  if ! "$FCLI_CMD" --version >/dev/null 2>&1; then
    printf 'Unable to execute fcli binary: %s\n' "$FCLI_CMD" >&2
    exit 127
  fi
}

ssc_require_command_help() {
  local description="$1"
  shift
  if ! "$FCLI_CMD" "$@" --help >/dev/null 2>&1; then
    printf 'This fcli build does not expose the expected command for %s: fcli %s\n' "$description" "$*" >&2
    printf 'Use the Fortify Lab recommended fcli v3 version or inspect fcli readiness.\n' >&2
    exit 2
  fi
}

ssc_confirmed() {
  local name="$1"
  [[ "${!name:-}" == "yes" ]]
}

ssc_require_appversion() {
  if [[ -z "${APPVERSION:-}" ]]; then
    printf 'APPVERSION is required and must use <application>:<version>, for example Fortify Lab Training:Synthetic.\n' >&2
    exit 2
  fi
  printf '%s' "$APPVERSION"
}

ssc_session_name() {
  printf '%s' "${SESSION_NAME:-fortifylab}"
}

ssc_print_target() {
  printf '  SSC session:             %s\n' "$(ssc_session_name)"
  printf '  Application version:     %s\n' "$1"
  printf '  fcli binary:             %s\n' "$FCLI_CMD"
}
