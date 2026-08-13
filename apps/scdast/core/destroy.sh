#!/bin/bash

CURRENT_DIR="$( dirname "${BASH_SOURCE[0]}" )"

source $FORTIFY_HOME_K8S/.env
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-destroy.sh"

fortify_helm_delete_if_exists "$NAMESPACE" sdast-core
