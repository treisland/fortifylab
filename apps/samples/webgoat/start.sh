#!/bin/bash

set -eo pipefail

CURRENT_DIR="$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=../common.sh
source "$CURRENT_DIR/../common.sh"

sample_app_load_env
FORTIFY_SAMPLE_WEBGOAT_IMAGE="${FORTIFY_SAMPLE_WEBGOAT_IMAGE:-webgoat/webgoat:latest}"
export FORTIFY_SAMPLE_WEBGOAT_IMAGE
sample_app_start "$CURRENT_DIR/manifest.yaml" WEBGOAT "${WEBGOAT:-}"
