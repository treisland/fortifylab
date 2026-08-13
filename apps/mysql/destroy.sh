#!/bin/bash

CURRENT_DIR="$( dirname "${BASH_SOURCE[0]}" )" 

#load the environment variables
source $FORTIFY_HOME_K8S/.env
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-destroy.sh"

fortify_helm_delete_if_exists "$NAMESPACE" mysql

fortify_kubectl_delete_file_ignore_not_found "$NAMESPACE" "$CURRENT_DIR/pvc.yaml"
