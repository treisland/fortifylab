#!/bin/bash

set -eo pipefail

CURRENT_DIR="$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=../common.sh
source "$CURRENT_DIR/../common.sh"

sample_app_destroy "$CURRENT_DIR/manifest.yaml"
