# ScanCentral DAST

## Purpose and users

ScanCentral DAST coordinates dynamic testing of a running web application.
DAST learners and application-security users define authorized lab targets and
review scan behavior; operators maintain Core, scanners, database connectivity,
SSC integration, and LIM capacity.

!!! danger "Test only authorized targets"

    Dynamic testing sends active requests that can change data, trigger
    workflows, or disrupt a target. Scan only isolated systems you own or have
    explicit permission to test.

## Data and interfaces

- **Data:** DAST Core stores its operational state in PostgreSQL. Scan findings
  participate in the SSC-centered application-security workflow; SSC remains
  the findings system of record for this lab.
- **UI/API:** use the configured `https://dast.<lab-domain>` interface for DAST
  workflows. Use SSC for the associated application/version findings and LIM
  for license-pool administration. Exact APIs are version-specific.
- **Scan role:** Core coordinates work; scanners send test traffic to the
  authorized target and communicate with Core. LIM supplies scanner license
  capacity.

## Dependencies

DAST has three product-level upstream paths in this lab:

1. **PostgreSQL → DAST Core** for DAST operational state.
2. **SSC ↔ DAST** for application-security integration; SSC itself depends on
   MySQL.
3. **LIM → DAST scanners** for the configured DAST license pool.

Accordingly the wizard verifies PostgreSQL, SSC, and LIM before DAST. The LIM
license and expected pool require post-deployment configuration.

## Failure symptoms

Symptoms include an unavailable DAST UI/API, Core database errors, scanners
that do not register, no license capacity, a scan that cannot start, target
reachability failures, or missing integration with the intended SSC context.
Check PostgreSQL, then SSC, then LIM license/pool state, then Core, scanner
registration, and finally the authorized target.

## Stop impact

Stopping a scanner removes scan capacity and can interrupt its active work.
Stopping Core makes the DAST control plane unavailable. Neither action is the
same as deleting PostgreSQL storage, but confirm scan state before stopping.
Stopping LIM or SSC can also make DAST unusable even if its pods remain running.

Next: [PostgreSQL](postgresql.md) · [LIM](lim.md) · [SSC](ssc.md)
