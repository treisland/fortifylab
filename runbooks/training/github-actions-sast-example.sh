#!/usr/bin/env bash
# fortifylab-runbook: true
# name: Generate GitHub Actions SAST example
# description: Creates a sample GitHub Actions workflow that demonstrates FCLI and ScanCentral SAST integration.
# domain: CI/CD examples
# category: CI/CD Examples
# risk: low
# order: 20
# requires: bash
# params:
#   - name: target_repo
#     description: Local repository path where .github/workflows/fortify-sast.yml should be written.
#     required: true
#   - name: app_version
#     description: SSC application version variable value to show in the handoff.
#     default: JuiceShop:training

set -euo pipefail

mkdir -p "${TARGET_REPO}/.github/workflows"
cat > "${TARGET_REPO}/.github/workflows/fortify-sast.yml" <<'YAML'
name: Fortify SAST

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  fortify-sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install FCLI
        run: |
          curl -L -o fcli.zip https://github.com/fortify/fcli/releases/latest/download/fcli-linux.zip
          unzip fcli.zip -d "$HOME/fcli"
          echo "$HOME/fcli/bin" >> "$GITHUB_PATH"

      - name: Login to SSC
        run: |
          fcli ssc session login \
            --url "${{ secrets.SSC_URL }}" \
            --ci-token "${{ secrets.SSC_CI_TOKEN }}"

      - name: Package and submit SAST scan
        run: |
          fcli sc-sast package --source . --output app.zip
          fcli sc-sast scan start \
            --publish-to-appversion "${{ vars.SSC_APP_VERSION }}" \
            --package app.zip
YAML

echo "Created ${TARGET_REPO}/.github/workflows/fortify-sast.yml"
echo
echo "Required GitHub secret:"
echo "  SSC_CI_TOKEN"
echo
echo "Recommended GitHub variables:"
echo "  SSC_URL=${SSC_URL:-https://ssc.example.test}"
echo "  SSC_APP_VERSION=${APP_VERSION}"
