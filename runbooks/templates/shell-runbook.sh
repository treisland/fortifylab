#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Example runbook
# description: Explain what this runbook does and when a Solutions Engineer should use it.
# category: Examples
# risk: low
# order: 100
# requires: bash
# params:
#   - name: app_name
#     description: Example application name. Parameter names become uppercase environment variables.
#     default: JuiceShop
#   - name: target_url
#     description: Example URL pulled from .env when available.
#     defaultFromEnv: SSC_URL
#     required: false

set -euo pipefail

echo "Runbook started"
echo "APP_NAME=${APP_NAME}"
echo "TARGET_URL=${TARGET_URL:-<unset>}"
