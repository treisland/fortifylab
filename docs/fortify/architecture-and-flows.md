# Architecture and workflow diagrams

These diagrams describe the single-node lab assembled by this repository. They
are learning and troubleshooting aids, not a production reference
architecture. Labels that use monospace names are the Helm releases,
StatefulSets, or Kubernetes Secrets used by the current scripts.

!!! warning "Lab and demo use only"

    Use synthetic data and authorized scan targets. The diagrams deliberately
    contain no credentials, license contents, private addresses, or customer
    data.

## Lab topology

```mermaid
flowchart TB
    learner[Lab user] -->|HTTPS| ingress[MicroK8s ingress]
    learner -->|observe resources| dashboard[Kubernetes Dashboard]
    ingress --> ssc[SSC]
    ingress --> sast[ScanCentral SAST controller]
    ingress --> lim[LIM]
    ingress --> dast[ScanCentral DAST API]
    ssc --> mysql[(MySQL)]
    dast --> postgres[(PostgreSQL)]
    sast --> worker[SAST worker]
    dast --> scanner[DAST scanner]
    scanner --> target[Authorized test target]
    lim -->|license pool| dast
```

**Text alternative.** A lab user reaches SSC, the ScanCentral SAST controller,
LIM, and the ScanCentral DAST API through MicroK8s ingress and observes cluster
resources through Kubernetes Dashboard. SSC stores data in MySQL. DAST stores
operational data in PostgreSQL and uses LIM licensing. The SAST controller
coordinates a SAST worker, while DAST coordinates a scanner that accesses only
an authorized test target.

## Enforced startup dependencies

Solid arrows below mean a readiness gate implemented by
`scripts/lib/dependency-health.sh` and invoked by a component start script.

```mermaid
flowchart LR
    mysql[mysql StatefulSet<br/>authenticated query] --> ssc[ssc-webapp StatefulSet<br/>application endpoint]
    ssc --> sast[scancentral-sast-controller<br/>scancentral-sast-worker-linux]
    postgres[postgresql StatefulSet<br/>authenticated query] --> core[DAST Core]
    ssc --> core
    lim[lim StatefulSet<br/>application endpoint] --> core
    core --> scanner[sdast-scanner-scancentral-dast-scanner]
```

**Text alternative.** MySQL readiness, including an authenticated query, gates
SSC. SSC StatefulSet and endpoint readiness gate ScanCentral SAST. PostgreSQL,
SSC, and LIM readiness all gate DAST Core. DAST Core workload and endpoint
readiness gate the DAST scanner. DAST Core readiness specifically checks the
`sdast-core-scancentral-dast-core-api`,
`sdast-core-scancentral-dast-core-globalservice`, and
`sdast-core-scancentral-dast-core-utilityservice` StatefulSets.

## Deployment order

```mermaid
flowchart LR
    host[Host and MicroK8s] --> certs[Certificates]
    certs --> dashboard[Kubernetes Dashboard]
    dashboard --> secrets[Kubernetes Secrets]
    secrets --> databases[mysql and postgresql]
    databases --> apps[ssc and lim]
    apps --> sast[scancentral-sast]
    apps --> core[sdast-core]
    core --> scanner[sdast-scanner]
    sast --> checks[Client connectivity checks]
    scanner --> checks
```

**Text alternative.** Prepare the host and MicroK8s first, followed by
certificates, Kubernetes Dashboard, and Kubernetes Secrets. Deploy the `mysql`
and `postgresql` releases before `ssc` and `lim`. Deploy `scancentral-sast`
after SSC is ready. Deploy `sdast-core` after PostgreSQL, SSC, and LIM are
ready, then deploy `sdast-scanner`. Finish with client connectivity checks.

## Static analysis flow

```mermaid
sequenceDiagram
    actor User as Authorized user or CI
    participant SSC as SSC
    participant Controller as ScanCentral SAST controller
    participant Worker as scancentral-sast-worker-linux
    User->>Controller: Submit approved analysis job
    Controller->>Worker: Dispatch job
    Worker-->>Controller: Return analysis result
    Controller-->>SSC: Integrate result with application version
    User->>SSC: Review findings
```

**Text alternative.** An authorized user or CI workflow submits an approved
analysis job to the ScanCentral SAST controller. The controller dispatches it
to the Linux worker, receives the analysis result, and integrates the result
with the relevant application version in SSC. The user reviews findings in
SSC. Authentication details are intentionally omitted.

## Dynamic analysis flow

```mermaid
sequenceDiagram
    actor User as Authorized tester
    participant SSC as SSC
    participant Core as ScanCentral DAST Core
    participant LIM as LIM
    participant Scanner as sdast-scanner
    participant Target as Authorized test target
    User->>Core: Configure approved scan
    Core->>LIM: Request configured license capacity
    Core->>Scanner: Dispatch scan
    Scanner->>Target: Exercise allowed web surface
    Scanner-->>Core: Return observations
    Core-->>SSC: Integrate scan result
    User->>SSC: Review findings
```

**Text alternative.** An authorized tester configures a scan in ScanCentral
DAST Core. Core uses the configured LIM license capacity and dispatches work to
the `sdast-scanner`. The scanner exercises only the authorized target and
returns observations to Core. The integrated result is made available in SSC
for review. PostgreSQL persistence and service credentials are supporting
dependencies and are not shown in this interaction sequence.

## Secret material flow

Arrows show controlled materialization and consumption, not readable values.

```mermaid
flowchart LR
    input[Operator-provided license and registry input] --> creator[scripts/create-secrets.sh]
    certs[scripts/create-certs.sh output] --> creator
    creator --> common[fortify-secrets]
    creator --> tls[tls and TLS-support Secrets]
    creator --> dast[scdast database, service, and SSC account Secrets]
    creator --> lim[lim administrator, pool, JWT, and certificate Secrets]
    creator --> registry[regcred]
    common --> ssc[ssc and scancentral-sast]
    tls --> apps[Ingress and application TLS consumers]
    dast --> core[sdast-core and sdast-scanner]
    lim --> core
    registry --> images[Helm-managed workloads]
```

**Text alternative.** Operator-provided license and registry inputs plus
certificate-generation output are consumed by `scripts/create-secrets.sh`.
That script materializes the shared `fortify-secrets`, TLS-related Secrets,
DAST database and service-account Secrets, LIM administrator/pool/JWT and
certificate Secrets, and the `regcred` image-pull Secret. Workloads consume
only the Secrets they require. Values must never be copied into Git,
diagnostics, diagrams, or command output.

## Recovery order

```mermaid
flowchart LR
    storage[Storage and persistent claims] --> db[MySQL and PostgreSQL]
    db --> pair[Matching SSC database and secret.key]
    pair --> services[SSC and LIM]
    services --> sast[ScanCentral SAST]
    services --> core[ScanCentral DAST Core]
    core --> scanner[ScanCentral DAST scanner]
    scanner --> verify[Endpoints, integration, and synthetic scan]
    sast --> verify
```

**Text alternative.** Recover storage and persistent claims before MySQL and
PostgreSQL. Restore SSC with its matching database and `secret.key`, then
recover SSC and LIM. Recover ScanCentral SAST and DAST Core next, followed by
the DAST scanner. Finally verify database queries, endpoints, integrations, and
an authorized synthetic scan. A snapshot is not recovery evidence until this
sequence has been tested.

For operational constraints, continue to [deployment and
lifecycle](../operations/deployment-and-lifecycle.md), [secrets and
licenses](../operations/secrets-and-licenses.md), and [backup and
recovery](../operations/backup-and-recovery.md).
