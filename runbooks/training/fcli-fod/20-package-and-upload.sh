#!/usr/bin/env bash
# fortifylab-runbook: true
# name: FoD package and upload SAST scan
# description: Packages source with fcli v3 and optionally uploads a SAST scan to a FoD release after explicit external-SaaS confirmation.
# domain: Fortify on Demand
# category: FCLI FoD Training
# risk: high
# order: 72
# requires: bash
# params:
#   - name: source_dir
#     description: Local source directory to package.
#     default: .
#   - name: package_file
#     description: Package zip path to create.
#     default: package.zip
#   - name: release
#     description: FoD release id or <application>:<release> / <application>:<microservice>:<release>.
#     defaultFromEnv: FOD_RELEASE
#     required: false
#   - name: confirm_external_fod_upload
#     description: Set yes to upload to external FoD SaaS after packaging.
#     default: no

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/fod-common.bash"

fod_require_fcli
fod_print_env_inventory

RELEASE_VALUE="$(fod_require_release)"
SOURCE_DIR="${SOURCE_DIR:-.}"
PACKAGE_FILE="${PACKAGE_FILE:-package.zip}"

fod_note "Package" "Creating a ScanCentral package with fcli v3. This is local work before any FoD upload."
printf 'Source directory: %s\n' "$SOURCE_DIR"
printf 'Package file:    %s\n' "$PACKAGE_FILE"

fcli fod action run package --source-dir "$SOURCE_DIR" --output "$PACKAGE_FILE"

if [[ ! -f "$PACKAGE_FILE" ]]; then
  printf 'Expected package was not created: %s\n' "$PACKAGE_FILE" >&2
  exit 1
fi

fod_note "Upload boundary" "FoD upload changes external SaaS tenant state."
if ! fod_external_confirmed CONFIRM_EXTERNAL_FOD_UPLOAD; then
  cat <<UPLOAD
Package created. Upload skipped.

To submit intentionally, rerun with:
  CONFIRM_EXTERNAL_FOD_UPLOAD=yes

Command shape:
  fcli fod sast-scan start --release "$RELEASE_VALUE" -f "$PACKAGE_FILE" --store scan
UPLOAD
  exit 0
fi

fod_note "Upload" "Starting FoD SAST scan and storing the scan variable as ::scan:: for this fcli data folder."
fcli fod sast-scan start --release "$RELEASE_VALUE" -f "$PACKAGE_FILE" --store scan

fod_note "Next" "Use 30-wait-and-status to wait on ::scan:: or inspect release scan state."
