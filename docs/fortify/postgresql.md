# PostgreSQL

## Purpose and users

PostgreSQL persists ScanCentral DAST operational data in this lab. It is
operator-managed infrastructure and is not a findings interface.

## Data and interfaces

- **Data:** its persistent volume contains DAST Core state. PostgreSQL major
  versions have on-disk compatibility boundaries, so an image-tag change is not
  a substitute for a documented database upgrade.
- **UI/API:** no learner-facing database UI is exposed. Operators use protected,
  authenticated checks and version-appropriate database tools.
- **Scan role:** PostgreSQL does not scan and does not replace SSC. It supports
  DAST Core while scanners test an authorized target and the integrated
  application-security workflow uses SSC.

## Dependencies

PostgreSQL requires Kubernetes storage, Secrets, scheduling, and cluster
networking. DAST Core waits for its StatefulSet and an authenticated query.
PostgreSQL is one of three upstream DAST requirements alongside SSC and LIM.

## Failure symptoms

Look for a pending or restarting database pod, an unbound volume, failed
authenticated queries, DAST Core database errors, or an unavailable DAST
interface. A healthy database does not prove that SSC, LIM, Core, scanners, or
the target are ready.

## Stop impact

Stopping PostgreSQL makes DAST Core unavailable and blocks DAST workflows. A
normal stop should retain persistent storage; deleting that storage destroys
DAST state and is a separate destructive action.

Next: [ScanCentral DAST](scancentral-dast.md) · [LIM](lim.md) · [SSC](ssc.md)
