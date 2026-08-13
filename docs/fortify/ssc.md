# Software Security Center (SSC)

## Purpose and users

SSC is the central application for organizing applications and versions,
receiving and reviewing findings, administering users, and integrating Fortify
scanning workflows. Developers and security analysts use it to understand and
triage findings; lab operators configure its integrations.

**SSC is the application-security and findings system of record for this lab.**
ScanCentral services perform or coordinate scans, but Kubernetes Dashboard,
LIM, and the databases do not replace SSC as the findings interface.

## Data and interfaces

- **Data:** application/version records, findings, workflow configuration, and
  other SSC-managed state are persisted in MySQL. SSC also uses protected
  encryption material; preserve the matching SSC `secret.key` with its data.
- **UI/API:** open the configured `https://ssc.<lab-domain>` URL. Use only APIs
  supported by the deployed SSC version and consult its matching product
  documentation for API details.
- **Scan role:** SSC receives and organizes results made available through the
  SAST and DAST integrations. It does not perform SAST worker analysis or send
  DAST scanner traffic itself.

## Dependencies

MySQL is a hard upstream dependency. The lab waits for both the MySQL workload
and an authenticated query before starting SSC. Ingress, DNS, TLS, storage,
license inputs, and Kubernetes Secrets must also be prepared. On
Traefik-backed MicroK8s ingress, SSC uses the shared mkcert wildcard certificate
for browser-facing TLS and Traefik service annotations plus a
`ServersTransport` for the HTTPS backend hop to `ssc-service`.

SSC is itself upstream of both ScanCentral SAST and the lab's ScanCentral DAST
integration. Start and diagnose it before either scanning system.

## Failure symptoms

Typical evidence includes an unavailable login page, database connection or
migration errors, failed readiness, or downstream ScanCentral authentication
and connectivity failures. A running SSC pod does not prove that login,
database access, or the application endpoint works.

Check MySQL first, then the SSC workload and application endpoint, and finally
ingress, DNS, and TLS. Never rotate `secret.key` as an incidental repair.

## Stop impact

Stopping SSC interrupts login, findings access, administration, and dependent
SAST/DAST integration. It does not intentionally erase MySQL data. Destroying
persistent storage or replacing the encryption key is a separate, destructive
action with a much larger recovery impact.

Next: [ScanCentral SAST](scancentral-sast.md) ·
[ScanCentral DAST](scancentral-dast.md) · [MySQL](mysql.md)
