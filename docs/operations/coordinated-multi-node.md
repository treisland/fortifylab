# Coordinated multi-node lab

Fortify Lab remains single-machine first. A default `local` cluster profile keeps
all wizard behavior on the current host and current Kubernetes context.
Advanced users can define named cluster profiles for planning, diagnostics, and
read-only remote readiness checks before intentionally operating against another
Kubernetes context.

## Supported model

A coordinated lab is one Fortify Lab installation that understands one or more
named target profiles. Each profile describes where the operator expects the lab
to run and which responsibilities belong to that target.

A profile can define:

- SSH host for read-only readiness checks.
- Kubernetes context expected for deployment and diagnostics.
- Node role, such as `single-node`, `control-plane`, `worker`, or `observer`.
- Enabled components for planning notes.
- Storage class expected by the lab.
- Ingress mode expected by the lab.

The wizard does not copy secrets to remote machines, bootstrap remote nodes, or
mutate remote hosts in the first implementation. Remote checks are intentionally
read-only.

## Configuration shape

The root `.env` owns shared lab identity and the active profile selector:

```bash
export FORTIFY_CLUSTER_PROFILE="local"
export FORTIFY_CLUSTER_PROFILE_NAMES="local remote-demo"
```

Each named profile uses an uppercase, underscore-normalized identifier:

```bash
export FORTIFY_CLUSTER_PROFILE_REMOTE_DEMO_ROLE="control-plane"
export FORTIFY_CLUSTER_PROFILE_REMOTE_DEMO_KUBE_CONTEXT="remote-demo"
export FORTIFY_CLUSTER_PROFILE_REMOTE_DEMO_SSH_HOST="lab-admin@remote-demo"
export FORTIFY_CLUSTER_PROFILE_REMOTE_DEMO_ENABLED_COMPONENTS="ssc sast_controller sast_sensor"
export FORTIFY_CLUSTER_PROFILE_REMOTE_DEMO_STORAGE_CLASS="nfs"
export FORTIFY_CLUSTER_PROFILE_REMOTE_DEMO_INGRESS_MODE="microk8s-traefik"
```

Leave `*_KUBE_CONTEXT` empty for the default local path. When a profile names a
context, deployment pre-flight blocks if the active `kubectl` context does not
match. This prevents accidentally deploying to the wrong cluster.

## SSH readiness scope

The wizard's read-only readiness check connects with batch SSH and inspects:

- Hostname and operating system.
- Presence of `docker`, `microk8s`, `kubectl`, `helm`, and `snap`.
- MicroK8s readiness when MicroK8s exists on the remote host.

It does not copy files, read secrets, write configuration, install packages, or
start/stop services.

## DNS and TLS considerations

All client-visible hostnames still come from `DOMAIN` and the derived URL values.
For a coordinated lab, make sure every client and every node that needs to call
lab URLs can resolve the configured hosts to the ingress endpoint for the
selected profile.

TLS remains tied to the configured hostnames. If a profile changes the effective
DNS target, regenerate or provide certificates that cover the same hostnames and
confirm the ingress controller is serving the expected certificate.

## Limitations

This first coordinated-lab milestone is a planning and safety layer. It does not create a multi-node Kubernetes cluster, join MicroK8s nodes, copy registry
credentials, distribute TLS private keys, or support independent Fortify Lab
instances from one wizard session.

Use independent lab checkouts when nodes are meant to run unrelated labs. Use a
coordinated profile only when one operator is intentionally managing one lab
across known targets.
