# Phase 5 preview release notes

Phase 5 expands the web console support APIs for live deployment triage while
keeping the assistant lane read-only.

Operator support additions:

- deployment status payloads include a deduplicated event timeline across
  contextual steps;
- deployment log payloads include pod state, restart counts, recent events,
  hints, and safe `kubectl logs`/`describe pod` command options;
- route payloads include DNS or hosts-entry hints based on ingress/configuration
  evidence and the detected node IP when available; and
- certificate payloads summarize Kubernetes TLS Secret inventory and Traefik
  default-certificate evidence without exporting private keys.

Boundary:

- these APIs do not mutate Kubernetes, CoreDNS, Traefik, client DNS, hosts
  files, or local trust stores;
- missing tools or unavailable cluster evidence are reported as warnings or
  `unknown` statuses instead of guessed results.
