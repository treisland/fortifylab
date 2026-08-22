#!/usr/bin/env bash
# Shared helper for FoD fcli training runbooks. Not directly discoverable.

set -euo pipefail

fod_note() {
  printf '\n[%s] %s\n' "$1" "$2"
}

fod_require_fcli() {
  if ! command -v fcli >/dev/null 2>&1; then
    printf 'fcli was not found on PATH. Use Tools and FCLI readiness before running this FoD runbook.\n' >&2
    exit 127
  fi
}

fod_value_state() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    printf 'set'
  else
    printf 'unset'
  fi
}

fod_print_env_inventory() {
  fod_note "FoD boundary" "Fortify on Demand is external SaaS. These runbooks may contact your FoD tenant when you explicitly run fcli commands."
  printf 'Detected fcli/FoD environment variables without printing values:\n'
  local name
  for name in \
    FCLI_DEFAULT_FOD_URL \
    FCLI_DEFAULT_CLIENT_ID \
    FCLI_DEFAULT_CLIENT_SECRET \
    FCLI_DEFAULT_FOD_SESSION \
    FCLI_DEFAULT_FOD_RELEASE \
    FOD_URL \
    FOD_CLIENT_ID \
    FOD_CLIENT_SECRET \
    FOD_TENANT \
    FOD_USER \
    FOD_PASSWORD \
    FOD_RELEASE
  do
    printf '  %-28s %s\n' "$name" "$(fod_value_state "$name")"
  done
}

fod_release_value() {
  if [[ -n "${RELEASE:-}" ]]; then
    printf '%s' "$RELEASE"
  elif [[ -n "${FOD_RELEASE:-}" ]]; then
    printf '%s' "$FOD_RELEASE"
  elif [[ -n "${FCLI_DEFAULT_FOD_RELEASE:-}" ]]; then
    printf '%s' "$FCLI_DEFAULT_FOD_RELEASE"
  fi
}

fod_require_release() {
  local release
  release="$(fod_release_value)"
  if [[ -z "$release" ]]; then
    printf 'Missing FoD release. Set RELEASE, FOD_RELEASE, or FCLI_DEFAULT_FOD_RELEASE.\n' >&2
    printf 'Use <application>:<release>, <application>:<microservice>:<release>, or a numeric release id.\n' >&2
    exit 2
  fi
  printf '%s' "$release"
}

fod_show_fcli_version() {
  fod_note "fcli" "Installed fcli version"
  fcli --version
}

fod_try_session_list() {
  fod_note "Session check" "Listing local FoD sessions if fcli supports it"
  if ! fcli fod session list; then
    printf 'No active FoD session was listed, or this fcli version does not support session list output in this shell.\n'
  fi
}

fod_login_if_requested() {
  if [[ "${LOGIN_IF_NEEDED:-false}" != "true" ]]; then
    printf 'Skipping login. Set LOGIN_IF_NEEDED=true only in a private shell when you want fcli to use configured FoD defaults.\n'
    return
  fi

  fod_note "Login" "Running fcli fod session login using fcli defaults/environment. Secrets are not echoed by this runbook."
  fcli fod session login
}

fod_external_confirmed() {
  local name="$1"
  local value="${!name:-}"
  [[ "$value" == "yes" ]]
}
