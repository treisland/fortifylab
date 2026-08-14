#!/bin/bash

set -eo pipefail

CURRENT_DIR="$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=../common.sh
source "$CURRENT_DIR/../common.sh"

sample_app_load_env
FORTIFY_SAMPLE_JUICE_SHOP_IMAGE="${FORTIFY_SAMPLE_JUICE_SHOP_IMAGE:-bkimminich/juice-shop:latest}"
export FORTIFY_SAMPLE_JUICE_SHOP_IMAGE
sample_app_start "$CURRENT_DIR/manifest.yaml" JUICE_SHOP "${JUICE_SHOP:-}"
