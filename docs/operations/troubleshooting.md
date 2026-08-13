# Troubleshooting by symptom

Start with the first unhealthy dependency. A failed consumer is usually a
symptom, so do not repeatedly restart it while its database, license service,
storage, or network path is unhealthy.

!!! important "Readiness is not application health"
    A `Running` pod, a successful rollout, or a present Kubernetes object only
    proves one layer. Continue until the application's bounded health probe
    succeeds. Conversely, a useful application may still be starting while its
    pod is not yet Ready; wait for the configured timeout before intervening.

Use **Operational guidance → Create sanitized diagnostics bundle** in the
wizard when evidence must be shared. The commands below are read-only, but raw
output can still contain local names. Do not paste Secret values, environment
variables, arbitrary logs, or license data into an issue.

## Fast symptom index

| Symptom | First investigation | Then |
|---|---|---|
| Pod is `Pending` | PVC binding and scheduling state | node capacity, then image pull |
| Pod is restarting | termination reason and readiness | first unhealthy dependency |
| `ImagePullBackOff` | pinned image name and registry entitlement | image-pull Secret presence |
| SSC unavailable | MySQL authenticated health | SSC workload, endpoint, ingress |
| SAST unavailable | SSC application health | controller token, controller, workers |
| DAST unavailable | PostgreSQL, SSC, and LIM | Core workloads/API, scanner registration |
| URL unavailable | client DNS | node, ingress, endpoint, TLS |
| Dashboard unavailable | Dashboard deployment/service | ingress, DNS, TLS, token scope |
| Configuration drift | tested `.env.example` profile | local `.env`, chart and running images |

## Pods remain Pending

1. Check the pod phase and its claim names without displaying environment data:

    ```bash
    microk8s kubectl -n fortify get pods
    microk8s kubectl -n fortify get pvc
    ```

2. If a claim is `Pending`, confirm the expected storage class exists and can
   provision or bind storage. Preserve the claim; deletion is not a repair.
3. If claims are bound, inspect node readiness and allocatable CPU/memory. A
   scheduling failure requires capacity or placement correction, not a pod
   restart.
4. If the status is `ErrImagePull` or `ImagePullBackOff`, follow [image pull
   failures](#image-pull-failures).
5. After correcting the root cause, allow the controller to retry. Rerun the
   component's **Start / Upgrade** action only when the dependency is healthy.

## Pods restart or never become Ready

1. Check restart counts with the wizard's environment overview or sanitized
   diagnostics bundle.
2. Inspect only the pod status and recent termination reason locally. Treat
   application logs as sensitive until reviewed; never attach arbitrary logs
   directly to a public issue.
3. Check the dependency chain in order. Database consumers may restart while
   their database is unavailable, and DAST consumers also depend on LIM and
   SSC.
4. Confirm the application health probe, not merely pod phase. The repository's
   dependency waits are bounded by `FORTIFY_HEALTH_TIMEOUT` (600 seconds by
   default).
5. Fix the earliest unhealthy layer and retry once. Repeated restarts do not
   repair corrupt data or incompatible database migrations.

## Image pull failures

1. Compare configured chart and image identifiers with
   [Versions and compatibility](versions-and-compatibility.md). Product, chart,
   and image versions are different identifiers.
2. Confirm that the pull Secret exists; do not print or decode it:

    ```bash
    microk8s kubectl -n fortify get secret regcred -o name
    ```

3. Verify the registry account has the required Fortify entitlement outside
   the wizard. A successful host-side `docker pull` proves the local Docker
   client can authenticate, but Kubernetes still needs a usable `regcred`
   Secret in the namespace. Rerun the Secrets step after `docker login` so the
   wizard materializes Docker Hub credentials instead of copying credential
   helper references that kubelet cannot use.
4. If credentials may have been exposed, rotate them at the registry and
   regenerate the Kubernetes Secret.
5. Do not switch to `latest`. Restore a pinned, tested image tag and rerun the
   failed Start / Upgrade action.

## Storage and claims

Check storage before databases and application consumers:

1. Node and MicroK8s Ready.
2. Expected storage class available.
3. Claims `Bound` with sufficient capacity.
4. MySQL/PostgreSQL StatefulSet Ready.
5. Authenticated, suppressed-output database probe succeeds.

Do not delete a PVC to clear `Pending`, restart loops, or version errors.
Persistent-data deletion is a separate destructive workflow and is appropriate
only for an explicitly disposable lab after backup or when intentionally
starting over.

## MySQL and SSC

1. Verify `mysql` StatefulSet readiness and its bound claim.
2. Use the wizard's dependency-aware Start / Upgrade path. `apps/ssc/start.sh`
   refuses to begin SSC migrations until both MySQL StatefulSet readiness and
   an authenticated `SELECT 1` succeed.
3. Check `ssc-webapp` readiness, then the SSC application endpoint, ingress,
   client DNS, and TLS in that order. A plain `Internal Server Error` or other
   HTTP 5xx response means ingress reached SSC but the application endpoint is
   unhealthy; inspect sanitized pod events/logs and database migration state
   before continuing to ScanCentral.
4. Client hosts/DNS entries must point to the lab node IP, not `127.0.0.1` or
   `127.0.1.1`. Loopback entries can make host-local curls misleading and block
   browser or external-client access.
5. Preserve the SSC database and matching `secret.key` as one recovery set.
   Never regenerate `secret.key` to fix authentication or startup errors.

## ScanCentral SAST

1. Establish MySQL and SSC application health first.
2. Confirm the SSC ControllerToken is configured by presence only. Never print
   or paste the token.
3. Check the `scancentral-sast-controller` before workers. Workers cannot
   become useful while the controller endpoint is unavailable.
4. After repairing SSC or token configuration, rerun SAST Start / Upgrade and
   wait for the bounded controller/worker readiness checks.

## PostgreSQL, LIM, and ScanCentral DAST

1. Verify PostgreSQL claim, StatefulSet, and authenticated query.
2. Verify SSC application health.
3. Verify LIM endpoint, DAST entitlement, and the configured default pool.
4. Check all DAST Core workloads, then the DAST API endpoint.
5. Check the scanner only after Core is healthy; scanner registration is the
   final application-level confirmation.

Do not use permissive TLS client flags as a repair. Correct hostname, ingress,
certificate, and trust configuration instead.

## DNS, ingress, URLs, and TLS

Follow one direction through the request path:

1. Client DNS or hosts entry resolves the configured hostname to the lab node.
2. The node is reachable on the intended port.
3. MicroK8s ingress is Ready and contains the expected host rule. In
   MicroK8s the `kubectl get ingress` `ADDRESS` column can be empty even when
   the nginx ingress controller is serving traffic; verify the host rule,
   ingress controller, and curl status instead of relying on that column alone.
4. The service has application-ready endpoints.
5. The certificate includes the requested hostname.
6. The dedicated lab client trusts the lab-local CA.

A name mismatch is not fixed by importing the CA, and an untrusted issuer is
not fixed by changing DNS. Never disable certificate verification. See
[Networking, URLs, and TLS](networking-and-tls.md).

## Kubernetes Dashboard

1. Verify the Dashboard deployment and service in its installed namespace.
2. Verify its ingress host, client DNS, and lab CA trust.
3. Generate a fresh bounded token from the wizard. A valid token does not prove
   network reachability, and a reachable page does not prove token scope.
4. Prefer the view-only token. Treat administrator and non-expiring tokens as
   credentials with full stated scope; never store them in Git or diagnostics.

## Configuration and version drift

Run **Operational guidance → Versions and compatibility**. `MATCH` compares the
configured value with `.env.example`; `DRIFT` means a local override, not
necessarily a failure. Also compare observed workload images because a Helm
release can differ from current configuration.

Before changing anything, record the configured and observed version
identifiers without credentials. Review component and database release notes.
Do not assume Helm rollback reverses schema changes. Return to the tested
profile only through a planned migration or a documented disposable-lab reset.

## Escalation evidence

Create the allow-listed archive described in [Sanitized
diagnostics](diagnostics.md), inspect it locally, and share only that minimum
evidence. Record the failed wizard step and the first unhealthy dependency in
plain language. Sanitization reduces risk; it cannot guarantee arbitrary
external text is safe.
