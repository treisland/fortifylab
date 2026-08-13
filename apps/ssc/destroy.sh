#!/bin/bash

CURRENT_DIR="$( dirname -- "${BASH_SOURCE[0]}" )"

#load the environment variables
source $FORTIFY_HOME_K8S/.env
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-destroy.sh"

fortify_helm_delete_if_exists "$NAMESPACE" ssc

microk8s kubectl -n "$NAMESPACE" delete ingress ssc-ingress --ignore-not-found
if microk8s kubectl get crd middlewares.traefik.io >/dev/null 2>&1; then
    microk8s kubectl -n "$NAMESPACE" delete middleware.traefik.io fortify-upload-buffer --ignore-not-found
fi
