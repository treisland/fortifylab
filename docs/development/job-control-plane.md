# Job control plane

The Fortify Lab web console should treat deployments, lifecycle changes,
configuration repairs, certificate work, diagnostics, and support exports as
typed jobs owned by the backend. The browser submits intent and observes
progress; it must not be the execution host.

This model keeps long-running work resumable, auditable, lock-aware, and safe
when browser tabs close, LAN connectivity drops, or multiple operators are
watching the same lab.

## Interaction model

Use this contract:

1. The UI submits a typed intent.
2. The backend validates permissions, configuration, and lock availability.
3. The backend creates a job with a stable identifier.
4. The backend executes steps, emits events, captures redacted logs, and records
   audit entries.
5. The UI polls or subscribes to job and event state.
6. The UI offers only backend-advertised next actions such as retry, cancel,
   pause, resume, view logs, repair, or diagnose.

Simple reads such as dashboard snapshots, help topics, service summaries, and
certificate metadata can remain direct API calls. Mutating, long-running, or
recoverable operations should use jobs.

## Typed intents

A job intent describes what the operator wants, not which shell script should
run. Examples:

- `guided_deploy`: run the guided deployment workflow for a profile.
- `guided_step`: run or retry one guided deployment step.
- `lifecycle`: start, stop, restart, destroy, shut down, or bring up a scope.
- `config_repair`: validate or repair derived `.env` host and URL values.
- `certificates`: generate, import, rotate, or verify certificates.
- `secrets`: create, refresh, verify, or rotate Kubernetes secrets.
- `diagnostics`: collect findings, inspect routes, or build a support bundle.
- `health_probe`: run a deeper service readiness or reachability check.

The UI should display friendly action names. Script paths, raw commands,
tokens, passwords, license contents, and private keys do not belong in normal
job cards.

## Scopes

Every job should declare the scope it may affect. Scopes drive locking,
permissions, audit language, and recovery messaging.

Common scopes:

- `lab`: the whole Fortify Lab environment.
- `cluster`: MicroK8s and cluster-level services.
- `service:<name>`: a Fortify Lab service such as SSC, LIM, MySQL, PostgreSQL,
  ScanCentral SAST, ScanCentral DAST, Dashboard, or Docs.
- `config`: `.env`, profiles, hostnames, URLs, and derived settings.
- `certificates`: root CA, leaf certificates, TLS secrets, and served
  certificate checks.
- `secrets`: Kubernetes secrets and registry credentials.
- `logs`: log collection or follow sessions.
- `diagnostics`: diagnostics and support bundle collection.

Scope names should stay stable so the UI can show meaningful "blocked by active
job" messages.

## States

Jobs and job steps should use a small shared state vocabulary:

- `queued`: accepted but not started.
- `running`: actively executing.
- `waiting`: waiting for an external condition such as pod readiness.
- `blocked`: cannot continue until the operator fixes something.
- `failed`: execution or verification failed.
- `complete`: execution and required verification completed.
- `canceled`: safely stopped before completion.

When a job command succeeds but verification fails, the job should not be shown
as simply successful. Prefer language such as "deployment command completed,
verification failed" with the failed verification attached.

## Locks and concurrency

The backend owns concurrency control. The UI may hide unavailable actions, but
the backend must enforce locks.

Lock rules:

- A whole-lab deployment blocks teardown, destroy, and conflicting lifecycle
  actions.
- A service lifecycle job blocks other mutating jobs for the same service.
- Certificate and secret rotation block dependent deployment steps.
- Read-only diagnostics and log views should be allowed unless they would
  interfere with a mutating job.
- Jobs should record which locks they hold and which active job blocked a
  rejected request.

Lock conflict responses should be explicit: actor if known, job type, scope,
started time, and safe next action.

## Events, logs, and audit

Use separate but linked streams:

- **Events:** machine-readable progress such as job queued, step started,
  waiting for pod readiness, finding detected, recovery offered, step complete,
  or job failed.
- **Logs:** redacted command output, job output, and linked Kubernetes pod logs.
- **Audit:** human-readable record of who requested what, when, from where, with
  what result.

Audit entries should include:

- actor and role when available;
- source such as web, CLI, or service;
- intent type and scope;
- requested action name;
- start, finish, and duration;
- result and verification outcome;
- affected resources;
- recovery or next action when relevant.

Logs, events, diagnostics, and support bundles must redact secrets, tokens,
passwords, license contents, private keys, and Docker credentials.

## Retry, cancel, pause, and resume

The backend should advertise supported controls per job and per step. The UI
should not infer that an action is safe.

- `retry`: available when the step is idempotent or has a known safe retry path.
- `cancel`: available only when the backend can stop without corrupting state.
- `pause`: available for guided workflows and auto-advance timers.
- `resume`: available when a paused or blocked workflow can continue.

Destructive jobs such as PVC deletion, teardown, and destroy actions must show
impact and irreversibility before submission. The confirmation model should be
natural in the UI, with deliberate controls rather than awkward typed phrases.

## Recovery

Failures should produce recovery suggestions, not only errors. Recovery
suggestions should be tied to the failed job, failed step, affected scope, and
current live state.

Examples:

- Traefik default certificate: recreate TLS secret, verify ingress TLS hosts,
  inspect served certificate.
- Image pull failure: refresh registry secret, verify Docker login, retry the
  affected service.
- Invalid `.env`: open configuration repair, show expected host and URL values,
  rerun validation.
- Service returns HTTP 500: inspect service logs, show pod restarts and recent
  events, retry readiness probe.
- Missing secrets: refresh secrets and rerun secret verification.

Recovery actions should be submitted as their own typed jobs so they are locked,
audited, and observable.

## Browser reconnect

The browser must be able to disconnect and reconnect without losing the
operation.

Requirements:

- Jobs have stable IDs and persisted state.
- The UI can list active and recent jobs.
- The UI can reopen a job detail view by ID.
- The UI marks stale snapshots with a last-updated time.
- If polling or streaming fails, the UI says the browser is disconnected while
  making clear that backend jobs may still be running.
- On reconnect, the UI should reconcile the active job with live cluster state
  and job events.

Polling is acceptable first. Server-sent events or WebSockets can be added later
for lower-latency updates, but they should use the same job/event model.

## UI responsibilities

The UI is responsible for:

- presenting friendly action names and impact summaries;
- submitting typed intents;
- displaying current job, step, event, log, audit, and recovery state;
- preserving operator context while live updates arrive;
- showing only backend-advertised controls;
- distinguishing live cluster state from historical job state;
- making disconnection, stale data, and blocked actions obvious.

The UI should avoid embedding execution rules, lock logic, command construction,
or secret handling.

## Backend responsibilities

The backend is responsible for:

- validating intents, configuration, permissions, and confirmations;
- creating durable job records and stable IDs;
- enforcing locks and concurrency rules;
- executing steps and probes;
- redacting output;
- recording events, logs, audit, verification, and recovery suggestions;
- exposing retry, cancel, pause, and resume capabilities;
- reconciling job state with live Kubernetes, Helm, filesystem, and service
  state.

The backend should be the source of truth for all mutating operations.

## UI surfaces that benefit from jobs

Jobs should back:

- Guided Deploy full workflow and individual steps;
- lifecycle start, stop, restart, destroy, teardown, shutdown, and bring-up;
- `.env` save, repair, backup, and rollback;
- TLS generation, import, rotation, and served-certificate verification;
- secret creation, registry credential refresh, and secret verification;
- pre-flight checks and image pull validation;
- diagnostics and support bundle export;
- deep service health checks;
- first-scan workflow steps;
- upgrade, migration, and repair operations.

Logs follow sessions may be long-lived sessions rather than finite jobs, but
they should share the same actor, scope, event, and audit conventions.

## Design principle

The web console should request intent; the backend should execute safely; the
operator should be able to watch progress, inspect logs, understand recovery,
and reconnect without losing context.
