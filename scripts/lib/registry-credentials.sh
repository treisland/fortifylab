#!/bin/bash
# Shared Docker registry credential helpers for Kubernetes imagePullSecrets.

registry_error() {
    if declare -F error >/dev/null 2>&1; then
        error "$*"
    else
        printf 'ERROR: %s\n' "$*" >&2
    fi
}

docker_config_path() {
    local path="${DOCKER_CONFIG_PATH:-$HOME/.docker/config.json}"
    if [ ! -f "$path" ] && [ -n "${SUDO_USER:-}" ]; then
        path="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.docker/config.json"
    fi
    printf '%s\n' "$path"
}

materialize_registry_auth_config() {
    local source_config output_config
    source_config="$(docker_config_path)"
    if [ ! -f "$source_config" ]; then
        registry_error "Docker config not found at $source_config"
        registry_error "Run docker login with an entitled account, then retry this step."
        return 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        registry_error "python3 is required to prepare Kubernetes image-pull credentials."
        return 1
    fi

    output_config="$(mktemp "${TMPDIR:-/tmp}/fortify-regcred.XXXXXX")"
    if python3 - "$source_config" "$output_config" <<'PYCODE'
import base64
import json
import shutil
import subprocess
import sys

source_path, output_path = sys.argv[1:3]
servers = [
    "https://index.docker.io/v1/",
    "registry-1.docker.io",
    "https://registry-1.docker.io",
    "index.docker.io",
    "docker.io",
]

def dockerhub_equivalent(value):
    normalized = value.replace("https://", "").replace("http://", "").rstrip("/")
    return normalized in {"index.docker.io/v1", "registry-1.docker.io", "index.docker.io", "docker.io"}

def encode_auth(username, secret):
    token = f"{username}:{secret}".encode("utf-8")
    return base64.b64encode(token).decode("ascii")

def entry_credentials(entry):
    if not isinstance(entry, dict):
        return None
    if entry.get("auth"):
        return {"auth": entry["auth"]}
    if entry.get("username") and entry.get("password"):
        return {"auth": encode_auth(entry["username"], entry["password"])}
    if entry.get("identitytoken"):
        return {"identitytoken": entry["identitytoken"]}
    return None

def helper_credentials(helper, server):
    helper_bin = shutil.which(f"docker-credential-{helper}")
    if not helper_bin:
        return None
    result = subprocess.run(
        [helper_bin, "get"],
        input=server,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    username = payload.get("Username")
    secret = payload.get("Secret")
    if username and secret:
        return {"auth": encode_auth(username, secret)}
    return None

with open(source_path, "r", encoding="utf-8") as handle:
    config = json.load(handle)

auths = config.get("auths") or {}
cred_helpers = config.get("credHelpers") or {}
creds_store = config.get("credsStore")

search_keys = []
for server in servers:
    if server not in search_keys:
        search_keys.append(server)
for key in auths:
    if dockerhub_equivalent(key) and key not in search_keys:
        search_keys.append(key)

credentials = None
for key in search_keys:
    credentials = entry_credentials(auths.get(key, {}))
    if credentials:
        break

if not credentials:
    for key in search_keys:
        helper = cred_helpers.get(key) or creds_store
        if not helper:
            continue
        credentials = helper_credentials(helper, key)
        if credentials:
            break

if not credentials:
    raise SystemExit(
        "Docker Hub credentials were not available as inline auth and no configured "
        "Docker credential helper returned credentials for Kubernetes. Run docker login "
        "again, or set DOCKER_CONFIG_PATH to a Docker config with inline Docker Hub auth."
    )

materialized = {"auths": {server: dict(credentials) for server in servers}}
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(materialized, handle, separators=(",", ":"))
PYCODE
    then
        printf '%s\n' "$output_config"
    else
        local rc=$?
        rm -f "$output_config"
        return "$rc"
    fi
}

refresh_registry_credentials() {
    local registry_config rc
    registry_config="$(materialize_registry_auth_config)" || return 1
    if [ -z "${KUBECTL:-}" ] || [ -z "${NAMESPACE:-}" ]; then
        registry_error "Kubernetes namespace or kubectl command is not configured for image-pull credentials."
        rm -f "$registry_config"
        return 1
    fi
    if declare -F cluster_reachable >/dev/null 2>&1; then
        cluster_reachable || {
            registry_error "Cluster not reachable while refreshing image-pull credentials."
            rm -f "$registry_config"
            return 1
        }
    fi

    $KUBECTL -n "$NAMESPACE" create secret generic regcred \
        --type=kubernetes.io/dockerconfigjson \
        --from-file=.dockerconfigjson="$registry_config" \
        --dry-run=client -o yaml | $KUBECTL -n "$NAMESPACE" apply -f -
    rc=$?
    rm -f "$registry_config"
    return "$rc"
}
