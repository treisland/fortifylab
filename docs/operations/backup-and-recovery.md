# Backup and recovery guidance

This lab has no production-grade backup, high availability, disaster recovery,
or restore guarantee. A filesystem or PVC snapshot alone may capture databases
mid-write and is not proof of application consistency.

## Before a risky change

1. Record the tested profile and observed chart/image/database versions.
2. Create database-native logical exports for MySQL/SSC and PostgreSQL/DAST
   using the applicable vendor guidance.
3. Protect the matching SSC `secret.key`, required configuration, public
   certificates, and private trust material through a channel outside Git.
4. Inventory claims by name and capacity without copying application data into
   the repository.
5. Store checksums and access instructions separately from the archives.
6. Restore into an isolated disposable lab and complete a synthetic scan.

Never add recovery artifacts to a diagnostics archive. The sanitized bundle
intentionally excludes Secrets, ConfigMaps, environment variables, license
metadata, and logs.

## Dependency-aware recovery

Recover in forward dependency order:

1. establish compatible MicroK8s and writable storage;
2. recover MySQL and PostgreSQL, then verify authenticated queries;
3. restore the matching SSC database and `secret.key` together;
4. start SSC and LIM and verify application endpoints and licensing;
5. start the SAST controller and workers;
6. start DAST Core and verify its API;
7. start the DAST scanner and verify registration;
8. verify ingress, DNS, TLS trust, Dashboard access, and a synthetic scan.

Do not start consumers while their recovered dependency is unhealthy. A
`Running` database pod is insufficient; require the authenticated,
suppressed-output query and then application-level checks.

## Recovery decisions

- **Workload missing, claim intact:** rerun Start / Upgrade for the tested
  version and verify the existing data through the application.
- **Configuration drift:** capture configured and observed versions, then plan
  a compatible forward change or restore the whole matching recovery set.
- **Database corruption or migration failure:** stop consumers, preserve the
  current evidence, and restore a verified database-native export. Helm
  rollback alone cannot reverse migrations.
- **SSC key mismatch:** stop SSC consumers and locate the `secret.key` that
  belongs to the restored SSC database. Generating a new key does not recover
  encrypted values.
- **Certificate trust failure:** restore the matching trust material or perform
  an explicit trust rotation. Do not bypass verification.
- **Disposable lab reset:** use Destroy only after accepting named data loss,
  then redeploy in dependency order. This is re-creation, not recovery.

## Data deletion boundary

Deleting persistent claims is irreversible through this wizard and remains
separate from Stop. Current database and LIM Destroy scripts delete claims, so
treat every Destroy choice as data-destructive. Never delete PVCs to repair
Pending pods, restart loops, or incompatible versions.

Database major-version changes may require a logical export/import. Do not
attach an old data directory to an incompatible image and do not assume a chart
downgrade makes an upgraded database readable.
