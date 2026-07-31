# License and Infrastructure Manager (LIM)

## Purpose and users

LIM supplies the DAST license-pool service used by scanners in this lab. Lab
operators install the entitled DAST license and manage the expected pool. Most
developers and security analysts do not need to administer LIM directly.

LIM is not a findings repository, scan-results UI, or replacement for SSC.

## Data and interfaces

- **Data:** license entitlement and pool configuration are security-sensitive.
  The repository also supplies protected credentials and certificate material
  for the LIM deployment. Documentation never displays their values.
- **UI/API:** open the configured `https://lim.<lab-domain>` URL to perform the
  product-supported license and pool setup. API behavior is version-specific.
- **Scan role:** a DAST scanner obtains capacity from the configured pool. LIM
  does not coordinate scans or review their findings.

## Dependencies

LIM requires its Kubernetes workload, storage, protected Secrets, certificates,
ingress, DNS, and TLS to be ready. DAST scanners depend on a responding LIM and
the configured pool; LIM does not depend on SSC for its findings data because
it does not own findings.

## Failure symptoms

Typical symptoms are an unavailable LIM interface, license or pool errors, or a
DAST scanner that cannot obtain capacity. Verify LIM workload and endpoint
health, then confirm the entitled license and expected pool through the LIM UI.
Do not print license content or credentials while diagnosing.

## Stop impact

Stopping LIM prevents scanners from obtaining or renewing the capacity needed
by their workflow and can block DAST work. It does not erase SSC findings or
PostgreSQL data. Confirm DAST activity before stopping LIM, and treat deletion
of persistent data or Secrets as a separate destructive operation.

Next: [ScanCentral DAST](scancentral-dast.md) · [SSC](ssc.md)
