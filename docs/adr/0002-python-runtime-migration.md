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

`./bin/fortifylab` is the supported Python CLI/TUI entrypoint.
`start_wizard.sh` remains a supported compatibility shim for the documented
legacy aliases through M8 instead of the place where application logic lives.

Phase 3.7-3.8 also establishes the dependency posture for the Python runtime.
The current clone-and-run CLI continues to work with the Python standard
library only. Richer CLI/TUI work may add a small, explicit dependency set:
Typer for command structure, Rich for terminal output, Textual for interactive
TUI screens, and Pydantic for typed configuration and operation contracts. These
dependencies are declared separately from the documentation toolchain so
operators can distinguish lab runtime needs from MkDocs publishing needs.

## Consequences

- Python modules become the preferred home for new application logic.
- Bash scripts remain as compatibility wrappers or low-level operation adapters
  during replacement.
- Existing script entrypoints should continue to work while their internals move
  behind Python commands.
- Tests must cover both the compatibility wrappers and the Python behavior they
  call.
- Fortify Lab remains CLI/TUI-focused; full visual cluster management stays with
  Kubernetes-native tools such as the Kubernetes Dashboard or Rancher.
- Phase 3 does not introduce a Fortify Lab web UI. Browser-based lab
  observation remains the job of Kubernetes Dashboard and product UIs.
- New Python dependencies must be conservative, documented, and optional until a
  specific Python workflow requires them.

## Alternatives considered

Go was considered for its single-binary distribution and static typing. It is a
reasonable future option if distribution becomes the main constraint, but it is
not the Phase 3 choice because Fortify Lab currently benefits more from fast
iteration, rich terminal libraries, straightforward subprocess orchestration,
and readable contribution paths.

Staying Bash-only was rejected for Phase 3. Bash remains valuable at the edges,
but the wizard has grown beyond simple shell-script state and screen handling.

## Compatibility policy

During Phase 3 after M7, user-facing Bash entrypoints are compatibility
launchers or low-level adapters:

- `./bin/fortifylab` is the primary supported Python CLI/TUI surface.
- `./start_wizard.sh` is a shim for `--help`, `doctor`, `status`,
  `help topic ...`, and `config-diagnostics` through M8.
- Existing app scripts continue to exist as low-level lifecycle adapters while
  Python replacements land.
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

Phase 3.7-3.10 implementation PRs target the CLI/TUI runway branch
`agent/phase-3.7-3.10-python-cli-tui`, created from `dev` after Phase 3.0-3.6
was accepted. This keeps Python CLI/TUI integration work reviewable without
touching `dev` or `main` directly.

Promotion sequence:

1. Merge Phase 3 feature PRs into `agent/phase-3.7-3.10-python-cli-tui`.
2. Manually test customer demo and workshop/classroom scenarios from
   `agent/phase-3.7-3.10-python-cli-tui`.
3. Open a PR from `agent/phase-3.7-3.10-python-cli-tui` to `dev` only after manual validation.
4. Promote `dev` to `main` after a second acceptance pass.

Failed Phase 3 slices should be reverted or amended on
`agent/phase-3.7-3.10-python-cli-tui`.
Do not repair the integration branch by pushing directly to `dev` or `main`.

## Dependency policy

The runtime dependency set is intentionally small:

- core CLI dependencies: Typer, Rich, and Pydantic;
- optional full TUI dependency: Textual;
- development and documentation dependencies remain outside the runtime set.

The standard-library CLI wrapper remains valid while these dependencies are
introduced. A command that needs optional TUI dependencies must fail with a clear
message that explains how to install the Python runtime dependencies instead of
breaking unrelated compatibility shim or clone-safe Python commands.
