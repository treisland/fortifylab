#!/usr/bin/env bash
# fortifylab-runbook: true
# name: SSC token guidance
# description: Shows how to prepare an SSC token environment variable for fcli runbooks without printing or storing token values.
# domain: Local lab: SSC
# category: FCLI authentication
# risk: low
# order: 25
# requires: bash
# params:
#   - name: token_env_var
#     description: Environment variable name expected by SSC fcli login runbooks.
#     default: FCLI_DEFAULT_SSC_TOKEN
#     required: true
#   - name: session_name
#     description: fcli SSC session name used by the local lab runbooks.
#     default: fortifylab
#     required: true

set -euo pipefail

: "${TOKEN_ENV_VAR:?TOKEN_ENV_VAR is required.}"
: "${SESSION_NAME:?SESSION_NAME is required.}"

case "$TOKEN_ENV_VAR" in
    *[!A-Za-z0-9_]*)
        echo "TOKEN_ENV_VAR must be a shell-safe environment variable name."
        exit 1
        ;;
esac

echo "SSC token guidance"
echo "  Token variable:          $TOKEN_ENV_VAR"
echo "  fcli SSC session:        $SESSION_NAME"
echo

if [ -n "${!TOKEN_ENV_VAR:-}" ]; then
    echo "Current shell:             $TOKEN_ENV_VAR is set"
else
    echo "Current shell:             $TOKEN_ENV_VAR is not set"
fi

cat <<EOF

Recommended local flow:
  1. In SSC, create an automation token with the least privileges needed for the demo.
  2. In a private terminal, export the token only for that shell:
       export $TOKEN_ENV_VAR='<paste token privately>'
  3. Run Local SSC login and discovery using session '$SESSION_NAME'.
  4. When finished, run Local SSC logout and session cleanup, then unset the token:
       unset $TOKEN_ENV_VAR

Never store SSC token values in .env, runbook parameters, diagnostics, screenshots, or committed files.
EOF
