# First-scan walkthrough: visible results in SSC

This walkthrough proves the complete learning path: a deliberately synthetic
input is scanned and its results are visible in the intended SSC application
version. A `Running` pod, accepted submission, or completed worker job is only
an intermediate signal.

!!! warning "Lab and demo use only"

    Use only non-sensitive sample source and an isolated training target that
    you own or are explicitly authorized to test. Do not submit employer or
    customer source. Do not scan public, third-party, shared, or production
    systems from this lab.

The product interfaces vary between tested Fortify versions. Use the matching
Fortify product documentation for field names that differ, while preserving
the safety and verification boundaries below.

## Before either scan

1. Complete the [zero-to-running deployment](../getting-started/index.md) and
   use the wizard status view to establish infrastructure and component health.
2. In SSC, create a disposable application named `Fortify Lab Training` and a
   version named `Synthetic`. Do not reuse a production application or version.
3. Record the application and version names. They are the destination you will
   verify after each scan.
4. If a prerequisite is unhealthy, stop at that boundary. Do not bypass TLS,
   broaden permissions, regenerate `secret.key`, or add workers to conceal an
   upstream failure. Follow [troubleshooting by symptom](troubleshooting.md).

## Synthetic SAST walkthrough

### 1. Establish SAST prerequisites

Confirm this dependency order:

1. MySQL answers the authenticated readiness check.
2. SSC is application-ready and its UI is reachable with trusted TLS.
3. The ScanCentral SAST controller is ready.
4. At least one SAST worker is registered and ready.

If the chain stops, use the [MySQL and SSC](troubleshooting.md#mysql-and-ssc)
or [ScanCentral SAST](troubleshooting.md#scancentral-sast) boundary. A healthy
controller without SSC connectivity cannot deliver the required result.

### 2. Configure the protected ControllerToken

In SSC, create a token of type `ScanCentralCtrlToken`. Then open the wizard and
choose **Advanced setup and configuration → Configure → Apply SSC
ControllerToken**. Paste it only into the wizard's hidden prompt.

The protected flow updates the Kubernetes Secret without placing the token in
the repository, `.env`, command arguments, screenshots, or diagnostics. Verify
only that configuration is present; never print or retrieve the token for a
health check. If authentication fails, replace it through the same protected
flow and follow the [SAST troubleshooting boundary](troubleshooting.md#scancentral-sast).

### 3. Create and submit synthetic source

Create a new directory outside any real project and download the intentionally
minimal [`SyntheticGreeting.java`](../examples/sast/SyntheticGreeting.java)
sample into it. Inspect the file before submission: it contains a final class,
a private constructor, and a `main` method that prints only the literal text
`Fortify Lab synthetic sample`.

The sample contains no credentials, proprietary logic, dependencies, or build
output. Obtain the ScanCentral client that matches the deployed SAST version,
then use its documented submission workflow to:

- select only the synthetic directory;
- identify the SSC application/version as `Fortify Lab Training` / `Synthetic`;
- use the configured controller URL and normal certificate verification; and
- submit one scan without adding custom rules or production artifacts.

Do not copy a version-specific command from another release: client flags and
authentication mechanisms can change. A rejected submission belongs at the
[SAST authentication/controller boundary](troubleshooting.md#scancentral-sast);
a queued job with no execution belongs at the worker-readiness boundary in the
same section.

### 4. Verify the SAST result in SSC

Wait for the job to finish, then open **Fortify Lab Training → Synthetic** in
SSC and locate the uploaded SAST artifact or scan record. Confirm its upload
time and scan type match this run. Zero findings are acceptable for this benign
sample; absence of a scan record is not.

If the worker completes but the record is absent, check the intended
application/version, then follow the [SSC and SAST result path](troubleshooting.md#scancentral-sast).

## Synthetic DAST walkthrough

### 1. Record explicit target authorization

Before entering a URL in DAST, record all of the following in your lab notes:

- the exact scheme, hostname, port, and allowed path;
- the target owner and the person granting authorization;
- the authorized time window;
- confirmation that the target is isolated, disposable, and contains no real
  users, credentials, or business data; and
- confirmation that active test traffic and possible data changes are allowed.

If any item is missing, **do not scan**. DNS resolution or network reachability
does not constitute authorization. This walkthrough intentionally does not
provide a public target.

### 2. Establish DAST prerequisites

Confirm this dependency order:

1. PostgreSQL answers its authenticated query.
2. SSC is application-ready.
3. LIM is reachable, holds the entitled DAST license, and contains the pool
   named by `LIM_POOL_NAME` (default `Default`).
4. All DAST Core workloads and the DAST API are ready.
5. A DAST scanner is registered and can obtain capacity from the LIM pool.
6. The authorized target is reachable from the scanner with valid DNS and TLS.

Use [PostgreSQL, LIM, and ScanCentral DAST
troubleshooting](troubleshooting.md#postgresql-lim-and-scancentral-dast) for the
first five boundaries and [DNS, ingress, URLs, and
TLS](troubleshooting.md#dns-ingress-urls-and-tls) for target reachability. Do
not disable certificate validation or substitute a different target to make a
probe pass.

### 3. Submit a conservative scan

In the DAST interface, create a disposable scan for the authorized URL and
associate it with `Fortify Lab Training` / `Synthetic` in SSC. Start with the
smallest supported scope:

- one exact host and the authorized path only;
- no additional domains, redirects to other hosts, or wildcard scope;
- the lowest practical concurrency and request rate;
- no credentials unless the authorization explicitly covers a dedicated
  synthetic account; and
- no custom payloads, destructive workflows, or out-of-band integrations.

Review the resolved scope in the product UI before submission. Stop the scan if
it leaves the authorized boundary or the target owner requests it. A scan that
cannot start belongs at the [Core, scanner, or LIM
boundary](troubleshooting.md#postgresql-lim-and-scancentral-dast); target errors
belong at the [network and TLS boundary](troubleshooting.md#dns-ingress-urls-and-tls).

### 4. Verify the DAST result in SSC

After DAST reports completion, open **Fortify Lab Training → Synthetic** in SSC
and locate the DAST scan record. Confirm its target, completion time, and scan
type match the authorized run. Zero findings are acceptable; a completed DAST
job with no SSC-visible record is not success. Check the SSC association first,
then follow the [DAST integration boundary](troubleshooting.md#postgresql-lim-and-scancentral-dast).

## Completion and cleanup

The exercise is complete only when both synthetic scan records are visible in
the intended SSC application/version. Record that evidence without tokens,
passwords, license material, source bundles, or session data. Remove the local
synthetic source, disposable DAST target data, and sample SSC application when
the demonstration retention period ends. Cleanup must not delete shared lab
databases or persistent volumes.
