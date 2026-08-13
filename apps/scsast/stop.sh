#!/bin/bash

source "$FORTIFY_HOME_K8S/.env"
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-scale.sh"

fortify_scale_statefulset_if_exists "$NAMESPACE" scancentral-sast-controller 0
fortify_scale_statefulset_if_exists "$NAMESPACE" scancentral-sast-worker-linux 0
