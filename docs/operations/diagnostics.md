# Sanitized diagnostics bundle

`operational_create_diagnostics_bundle OUTPUT_DIRECTORY` creates a local
timestamped archive containing the lab disclaimer, dependency plan, and narrow
Kubernetes status tables. The directory must already exist and be writable.

The collector is bounded and read-only against Kubernetes. It deliberately
excludes logs, Secret and ConfigMap objects/data, environment variables,
commands/arguments, events, license metadata, local configuration, and file
paths. A final sanitizer redacts credential-shaped assignments, authorization
headers, and home-directory paths. Inspect every archive before sharing;
sanitization reduces risk but cannot prove arbitrary external text is safe.

When MicroK8s is offline, the archive records that status and completes without
trying to start it. Creating the local archive is the only mutation.
