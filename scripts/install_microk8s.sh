#!/bin/bash

set -euo pipefail

if [ -z "${FORTIFY_HOME_K8S:-}" ]; then
    FORTIFY_HOME_K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    export FORTIFY_HOME_K8S
fi

# Load the environment variables.
source "$FORTIFY_HOME_K8S/.env"

sudo apt install -y util-linux-extra
sudo snap install microk8s --classic

target_user="${SUDO_USER:-$USER}"
target_home="$(getent passwd "$target_user" | cut -d: -f6)"
sudo usermod -aG microk8s "$target_user"
if [ -n "$target_home" ]; then
    sudo mkdir -p "$target_home/.kube"
    sudo chown -R "$target_user:$target_user" "$target_home/.kube"
fi

# Used for dynamic provisioning of persistent volumes.
sudo apt install nfs-common -y

# Enable the ability to get community add-ons.
sudo microk8s enable community

# Enable NFS dynamic provisioning of persistent volumes (requires nfs-common).
sudo microk8s enable nfs

# Enable the Kubernetes Dashboard for a web UI.
sudo microk8s enable dashboard

# Let pods communicate via service names.
sudo microk8s enable dns

# Allow ingress endpoints.
sudo microk8s enable ingress

# Start the cluster.
sudo microk8s start
sudo microk8s status --wait-ready

cat <<EOF

MicroK8s is installed and $target_user has been added to the microk8s group.
If this shell cannot run microk8s yet, return to the wizard prerequisite menu
and choose 'g', or run: newgrp microk8s

EOF
