# Sanitized diagnostics bundle

From the wizard, choose **Operational guidance → Create sanitized diagnostics
bundle**. The wizard creates a private directory at
`${XDG_STATE_HOME:-$HOME/.local/state}/fortify-lab/diagnostics`, sets mode 700,
and calls the same function documented below.

For a deliberate shell invocation, source the library and provide an existing,
writable output directory:

```bash
export FORTIFY_HOME_K8S="$PWD"
source scripts/lib/operational-help.sh
mkdir -p "$HOME/.local/state/fortify-lab/diagnostics"
chmod 700 "$HOME/.local/state/fortify-lab/diagnostics"
operational_create_diagnostics_bundle "$HOME/.local/state/fortify-lab/diagnostics"
```

The function creates a timestamped `fortify-lab-diagnostics-*.tar.gz`. Creating
that local archive is its only mutation. Kubernetes collection is read-only and
bounded by `FORTIFY_OPERATION_TIMEOUT` (10 seconds by default). If MicroK8s is
offline, collection records that fact and completes without starting it.

## Exact allow-list

Every archive contains exactly:

- `README.txt`: lab-use warning, UTC creation time, included evidence, and exclusions;
- `deployment-plan.txt`: dependency order and preview-only statement;
- `cluster-profile.txt`: selected advanced cluster profile, expected kube context, SSH host label, storage class, and ingress mode;
- `doctor-summary.txt`: compact read-only health summary ordered by dependency;
- `network-diagnostics.txt`: host resolution, CoreDNS drift status, ingress class,
  service endpoint, and HTTP status-only checks;
- `kubernetes-evidence.txt`: describe-style summaries for nodes, workloads, pods,
  services, endpoints, persistent-volume claims, ingress hostnames/classes, and
  recent namespace events;
- `wizard-log-excerpt.txt`: bounded sanitized wizard log excerpt, or the reason it
  was unavailable.

The collector deliberately excludes Kubernetes Secret data, ConfigMap data, pod/application logs, environment variables, container command arguments, tokens, license contents,
registry credentials, TLS private keys, database exports, local configuration, and
source file paths. Recent Kubernetes events are included because they explain scheduling,
image pull, endpoint, and ingress failures without collecting pod logs. A final sanitizer
redacts credential-shaped assignments, authorization headers, and common home-directory
paths.

## Inspect before sharing

List and extract the archive only on a protected workstation. Read all files before sending them anywhere. Sanitization reduces risk but cannot prove
arbitrary command output is safe. Do not append raw logs, `.env`, decoded
Secrets, license data, tokens, certificates/private keys, or database exports.

When reporting a failure, add only a plain-language description of the failed
wizard step and first unhealthy dependency. Rotate any credential that may
already have been disclosed.
