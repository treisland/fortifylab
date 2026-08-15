#!/usr/bin/env bash
set -euo pipefail

ROOT="${FORTIFY_HOME_K8S:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
template="$ROOT/scripts/systemd/fortifylab-web.service.in"
out="${1:-$ROOT/.fortifylab/systemd/fortifylab-web.service}"
mkdir -p "$(dirname "$out")"
cp "$template" "$out"
printf 'Rendered %s
' "$out"
printf 'Review it, then install manually with: systemctl --user link %s && systemctl --user enable --now fortifylab-web.service
' "$out"
