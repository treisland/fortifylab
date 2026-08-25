#!/usr/bin/env bash
# Compatibility shim for the Python TUI migration.
#
# The Bash wizard implementation has been intentionally retired on the
# migration branch. Use ./bin/fortifylab as the primary entrypoint.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$repo_root/bin/fortifylab" "$@"
