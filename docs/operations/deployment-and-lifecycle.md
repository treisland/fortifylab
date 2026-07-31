# Deployment, resume, and lifecycle safety

The dependency order is host/MicroK8s → certificates → Dashboard → Secrets →
MySQL and PostgreSQL → SSC and LIM → SAST → DAST Core → DAST scanner → client
connectivity checks. The preview is descriptive and makes no changes.

The unfinished-work summary reports Kubernetes resource **presence**, not
health. Resume at the first missing dependency, then use the existing layered
health gates. A failed consumer must not be started until its dependency is
healthy.

- **Stop** retains persistent data.
- **Restart** cycles workloads and is not data repair.
- **Retry/repair** reruns a safe step after its root dependency is fixed.
- **Uninstall** removes application resources according to its documented scope.
- **Delete data** is a separate, explicitly confirmed action. Never imply it by
  “stop,” “restart,” or a routine uninstall.

Do not rotate SSC `secret.key`, database credentials, tokens, or trust roots as
incidental repair work. Helm rollback does not reverse database migrations.
