# Kubernetes Dashboard

## Purpose and users

Kubernetes Dashboard is the lab's optional browser interface for observing and
administering Kubernetes resources such as pods, workloads, events, and
resource status. Lab operators use it for cluster-level evidence.

**Kubernetes Dashboard is not a Fortify product.** It does not submit scans,
explain findings, manage Fortify applications, or replace the SSC, DAST, and
LIM product interfaces.

## Data and interfaces

- **Data:** it reads Kubernetes API resources allowed by the selected service
  account. Administrator access can expose Secrets and mutate or delete the
  entire lab; view-only access is the normal choice.
- **UI/API:** open `https://dashboard.<lab-domain>` and generate a token from
  the wizard's Dashboard access menu. Prefer a one-hour view-only token. Never
  commit, log, or share bearer tokens.
- **Scan role:** none. Dashboard reports cluster evidence only. A Running pod
  is not proof that a Fortify application login, database query, integration,
  or scan works.

## Dependencies

Dashboard depends on Kubernetes, its namespace and service, ingress, DNS, TLS,
and an explicitly generated access token. On Traefik-backed MicroK8s ingress,
the Dashboard route uses the shared mkcert wildcard certificate from
`fortify/tls` for browser-facing TLS and Traefik service annotations for the
HTTPS hop to the Dashboard service. It observes the other components but is not
in their runtime dependency path: Fortify applications can continue to run
while Dashboard is stopped.

## Failure symptoms

An inaccessible URL, certificate or DNS error, invalid or expired token,
authorization error, or missing resource commonly points to Dashboard routing,
identity, or permissions—not to SSC or a scanner failure. Check the namespace,
service, ingress, client DNS, TLS trust, and token scope in that order.

## Stop impact

Stopping Dashboard removes this browser-based cluster view but does not stop
SSC, ScanCentral, LIM, or the databases. Persistent tokens remain credentials
until explicitly revoked even when the UI is unavailable; prefer short-lived
tokens and revoke persistent tokens when their task ends.

Next: [SSC](ssc.md) · [Knowledge Center overview](index.md)
