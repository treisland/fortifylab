# Fortify lab operational help

> **LAB / DEMO USE ONLY.** This repository's deployment architecture is for
> evaluation, demonstrations, and training. It is not production guidance and
> does not make production availability, security, backup, recovery, or support
> claims about this lab automation. This limitation applies to this repository,
> not to Fortify products. Do not use production credentials, source code,
> customer data, or scan results here.

The shell entry points in `scripts/lib/operational-help.sh` are read-only unless
their name explicitly says that they create a local diagnostics bundle. Source
the file, then call:

```bash
operational_environment_overview
operational_deployment_plan
operational_unfinished_summary
operational_troubleshooting_topic pending-pods
operational_print_urls
operational_lifecycle_help
operational_secret_help
operational_version_help
operational_create_diagnostics_bundle ./support-output
```

These functions are designed for later wiring into wizard menus. They never
start MicroK8s, install or upgrade components, rotate credentials, or delete
resources. Cluster calls have a 10-second default bound. Offline documentation
and summaries remain usable when MicroK8s is unavailable.

## Guides

- [Deployment, resume, and lifecycle safety](deployment-and-lifecycle.md)
- [Networking, URLs, and TLS](networking-and-tls.md)
- [Troubleshooting by symptom](troubleshooting.md)
- [Secrets and licenses](secrets-and-licenses.md)
- [Backup and recovery](backup-and-recovery.md)
- [Versions and compatibility](versions-and-compatibility.md)
- [Sanitized diagnostics](diagnostics.md)
- [First scan walkthrough](first-scan.md)
- [Web console manual test notes](web-console-manual-tests.md)
