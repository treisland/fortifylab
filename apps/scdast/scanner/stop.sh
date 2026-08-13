#!/bin/bash

source "$FORTIFY_HOME_K8S/.env"
source "$FORTIFY_HOME_K8S/scripts/lib/k8s-scale.sh"

fortify_scale_statefulset_if_exists "$NAMESPACE" sdast-scanner-scancentral-dast-scanner 0
