#!/bin/bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

python3 scripts/validate_docs.py
python3 -m unittest discover -s tests -p 'test_*.py'

if [ -n "${MKDOCS_BIN:-}" ]; then
    "$MKDOCS_BIN" build --strict
elif [ -x .venv/bin/mkdocs ]; then
    .venv/bin/mkdocs build --strict
else
    python3 -m mkdocs build --strict
fi
