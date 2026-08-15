# ADR 0002: Python runtime migration

Status: Accepted

## Context

Fortify Lab began as a Bash-first wizard and deployment toolkit. Phase 2 made
that Bash implementation safer and more modular, but the guided deployment
experience now has application-level responsibilities: live progress rendering,
step state, retries, diagnostics, configuration repair, runbooks, logs, and
operator handoff flows.

The primary Phase 3 users are customer demo environments and
workshop/classroom operators. They need a calm guided experience, clear failure
recovery, and predictable clone-and-run setup more than they need a compiled
single binary.

## Decision

Fortify Lab will migrate its application runtime to Python during Phase 3.
Python is the accepted implementation language for the new core engine, CLI,
guided TUI, diagnostics, configuration engine, and operation command layer.

The repository remains clone-and-run in Phase 3. Packaging formats such as
`pipx`, `.deb`, containers, or single-file binaries are deferred until the
Python core is stable and the operator workflow is proven.

`start_wizard.sh` remains a supported compatibility entrypoint. Over time it
should become a thin launcher for the Python guided experience instead of the
place where application logic lives.

## Consequences

- Python modules become the preferred home for new application logic.
- Bash scripts remain as compatibility wrappers and short-lived adapters during
  replacement.
- Existing script entrypoints should continue to work while their internals move
  behind Python commands.
- Tests must cover both the compatibility wrappers and the Python behavior they
  call.
- Fortify Lab remains CLI/TUI-focused; full visual cluster management stays with
  Kubernetes-native tools such as the Kubernetes Dashboard or Rancher.

## Alternatives considered

Go was considered for its single-binary distribution and static typing. It is a
reasonable future option if distribution becomes the main constraint, but it is
not the Phase 3 choice because Fortify Lab currently benefits more from fast
iteration, rich terminal libraries, straightforward subprocess orchestration,
and readable contribution paths.

Staying Bash-only was rejected for Phase 3. Bash remains valuable at the edges,
but the wizard has grown beyond simple shell-script state and screen handling.

## Compatibility policy

During Phase 3, user-facing Bash entrypoints are compatibility launchers:

- `./start_wizard.sh` continues to start the normal guided workflow.
- Existing app scripts continue to exist while Python replacements land.
- A Bash script can become a wrapper once its behavior is covered by Python
  tests and the wrapper preserves documented arguments and exit behavior.
- Removing a Bash entrypoint requires a later explicit compatibility decision.

## State model

Live Kubernetes, Helm, and host state remain authoritative for deployed
resources. Local Python state may store only wizard/session metadata, including:

- selected deployment profile;
- selected cluster profile;
- current or last failed guided step;
- auto-advance preference;
- last diagnostics bundle path;
- wizard log references.

Local state must not store credentials, decoded Kubernetes Secrets, license
contents, registry tokens, TLS private keys, or raw application logs.

## Integration runway

Phase 3 implementation PRs target `integration/cli-phases-2.7-3.6`. That branch was created
from current `dev` and integrates accepted Phase 2 and Phase 3.0-3.6 work so Python migration work includes all accepted Phase
2 behavior without touching `dev` or `main`.

Promotion sequence:

1. Merge Phase 3 feature PRs into `integration/cli-phases-2.7-3.6`.
2. Manually test customer demo and workshop/classroom scenarios from
   `integration/cli-phases-2.7-3.6`.
3. Open a PR from `integration/cli-phases-2.7-3.6` to `dev` only after manual validation.
4. Promote `dev` to `main` after a second acceptance pass.

Failed Phase 3 slices should be reverted or amended on `integration/cli-phases-2.7-3.6`.
Do not repair the integration branch by pushing directly to `dev` or `main`.
