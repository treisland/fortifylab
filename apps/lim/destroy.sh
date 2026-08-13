#!/bin/bash

set -eo pipefail

# Get the current directory where this script resides
CURRENT_DIR="$( dirname -- "${BASH_SOURCE[0]}" )"

#load the environment variables
source $FORTIFY_HOME_K8S/.env
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-destroy.sh"

fortify_helm_delete_if_exists "$NAMESPACE" lim

fortify_kubectl_delete_file_ignore_not_found "$NAMESPACE" "$CURRENT_DIR/pvc.yaml"

microk8s kubectl -n "$NAMESPACE" delete ingress lim-ingress --ignore-not-found
