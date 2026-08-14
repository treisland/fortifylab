#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Show resolved lab URLs
# description: Prints the FortifyLab URLs currently derived from .env without showing credentials.
# category: Diagnostics
# risk: low
# order: 10
# requires: bash

set -euo pipefail

echo "FortifyLab URLs"
echo "SSC:        ${SSC_URL:-<unset>}"
echo "LIM:        ${LIM_URL:-<unset>}"
echo "SAST:       ${SCSAST_CTRL_URL:-<unset>}"
echo "DAST:       ${SCDAST_URL:-<unset>}"
echo "Dashboard:  ${DASHBOARD_URL:-<unset>}"
echo "JuiceShop:  ${JUICE_SHOP_URL:-<unset>}"
echo "WebGoat:    ${WEBGOAT_URL:-<unset>}"
echo "DVWA:       ${DVWA_URL:-<unset>}"
