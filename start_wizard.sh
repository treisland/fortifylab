#!/usr/bin/env bash
# Compatibility shim for the Python TUI migration.
#
# The Bash wizard implementation has been intentionally retired on the
# migration branch. Use ./bin/fortifylab as the primary entrypoint.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

has_flag() {
    local expected="$1"
    shift
    local arg
    for arg in "$@"; do
        [[ "$arg" == "$expected" ]] && return 0
    done
    return 1
}

case "${1:-}" in
    -h|--help)
        exec "$repo_root/bin/fortifylab" --help
        ;;
    config-diagnostics)
        shift
        exec "$repo_root/bin/fortifylab" config diagnostics "$@"
        ;;
    doctor)
        shift
        if has_flag "--help" "$@" || has_flag "--check" "$@"; then
            exec "$repo_root/bin/fortifylab" doctor "$@"
        fi
        exec "$repo_root/bin/fortifylab" doctor --check "$@"
        ;;
    status)
        shift
        if has_flag "--help" "$@" || has_flag "--check" "$@"; then
            exec "$repo_root/bin/fortifylab" status "$@"
        fi
        exec "$repo_root/bin/fortifylab" status --check "$@"
        ;;
    help)
        shift
        if [[ "${1:-}" == "topic" ]] && ! has_flag "--help" "$@" && ! has_flag "--check" "$@"; then
            exec "$repo_root/bin/fortifylab" help "$@" --check
        fi
        exec "$repo_root/bin/fortifylab" help "$@"
        ;;
esac

exec "$repo_root/bin/fortifylab" "$@"
