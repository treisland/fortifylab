# Fortify Lab Help Center

These offline topics support the wizard's Help and Fortify Knowledge Center.
They explain the lab architecture without querying or changing the host,
Kubernetes cluster, credentials, or Fortify applications.

Start with:

- [System overview](overview.txt)
- [Dependencies and data flow](architecture.txt)
- [Software Security Center](ssc.txt)
- [ScanCentral SAST](sast.txt)
- [ScanCentral DAST](dast.txt)
- [License and Infrastructure Manager](lim.txt)
- [MySQL](mysql.txt) and [PostgreSQL](postgresql.txt)
- [Kubernetes Dashboard](dashboard.txt)
- [Roles and learning paths](roles.txt)
- [Glossary](glossary.txt)
- [URLs and interfaces](urls.txt)
- [Lab deployment versus Fortify products](lab-scope.txt)

Operational procedures, troubleshooting, recovery guidance, sanitized
diagnostics, and the first-scan walkthrough are under
[`docs/operations`](../operations/README.md). The mandatory lab/demo boundary
and acknowledgement behavior are documented in [Lab use](../lab-use.md).

Keep component names, dependency claims, URLs, and version-sensitive behavior
aligned with `start_wizard.sh`, `.env.example`, and the corresponding tests.
