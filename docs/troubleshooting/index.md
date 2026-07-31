# Troubleshooting

Start with [troubleshooting by symptom](../operations/troubleshooting.md). It
separates a root dependency failure from the downstream components it blocks
and suggests safe checks before a retry.

If more evidence is needed, create the deliberately minimal bundle described in
[sanitized diagnostics](../operations/diagnostics.md). Review every archive
before sharing it. The bundle intentionally excludes logs, Kubernetes Secret
and ConfigMap data, environment variables, command lines, credentials, license
metadata, and local configuration paths.

The [offline Help Center](../help/README.md) remains available when MicroK8s or
the network is unavailable.
