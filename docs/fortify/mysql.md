# MySQL

## Purpose and users

MySQL is SSC's persistent database in this lab. It is operator-managed
infrastructure, not a normal learner-facing Fortify interface.

## Data and interfaces

- **Data:** it persists SSC-managed application, findings, configuration, and
  related state. Backups must be coordinated with the matching SSC encryption
  material and the guidance for the deployed versions.
- **UI/API:** the lab exposes no learner-facing MySQL UI. Operators use narrow,
  authenticated readiness checks and approved database tools; do not expose the
  database publicly or manually edit the SSC schema.
- **Scan role:** MySQL does not scan. It supports SSC, which is the findings
  system of record and an upstream dependency of the SAST/DAST integrations.

## Dependencies

MySQL requires working Kubernetes storage, Secrets, scheduling, and cluster
networking. SSC waits for the MySQL StatefulSet and an authenticated query.
This makes MySQL the first product-data dependency in the **MySQL → SSC →
SAST/DAST** paths.

## Failure symptoms

Evidence includes a pending or restarting database pod, an unbound volume,
failed authenticated queries, SSC connection or migration errors, and cascading
ScanCentral failures. Database pod readiness alone does not prove SSC health.

## Stop impact

Stopping MySQL makes SSC unavailable and therefore disrupts dependent SAST and
DAST integration. A normal workload stop should retain its persistent volume;
deleting storage destroys SSC data and is not a troubleshooting step.

Next: [SSC](ssc.md) · [ScanCentral SAST](scancentral-sast.md) ·
[ScanCentral DAST](scancentral-dast.md)
