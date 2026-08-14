# Phase 3 Python migration

Phase 3 turns Fortify Lab from a Bash-centered wizard into a Python application
while preserving the clone-and-run workflow used for demos and classrooms.

## Primary operators

Phase 3 optimizes for:

- customer demo environments;
- workshop and classroom labs;
- Solutions Engineers and instructors;
- the individual lab operator running a disposable Fortify training lab.

The project still favors explicit lab safety, synthetic data, and predictable
manual recovery over unattended production automation.

## Branching model

`integration/phase-3` is the active Python migration runway. It starts from
`integration/phase-2` and includes the full Phase 2 stack. Feature branches for
Phase 3 should target `integration/phase-3`.

`dev` and `main` stay untouched until manual testing accepts the integrated
Phase 3 branch.

Promotion flow:

```text
agent/phase-3.x-* -> integration/phase-3 -> dev -> main
```

## Runtime direction

Python owns new application behavior. Bash stays at the edges as wrappers for
existing commands until each behavior has a Python implementation and tests.

Preferred order:

1. Architecture and compatibility records.
2. Python package and CLI foundation.
3. Guided deployment TUI prototype.
4. Python deployment orchestration model.
5. Python configuration engine.
6. Python diagnostics engine.
7. Python replacement of deployment operations.
8. Remote LAN companion web console.
9. Packaging and upgrade hardening.

## Guided TUI prototype

Phase 3.2 introduces a Python guided deployment TUI prototype as an opt-in
preview through `./bin/fortifylab tui --demo-screen`. The prototype owns the
Python screen model, smooth in-place rendering primitives, auto-advance control
labels, contextual log and diagnostics entry points, and deployment profile data.
It does not execute live deployment operations yet; `./start_wizard.sh` remains
the production guided deployment path until later Phase 3 work replaces each
behavior with tested Python modules.

## Deployment orchestration model

Phase 3.3 adds a Python orchestration model for dependency-ordered deployment
steps, resumable guided session metadata, retry/timeout/cancellation semantics,
and dry-run mapping to the existing Bash deployment scripts. The model is
inspectable with `./bin/fortifylab deploy --plan <profile>` and does not mutate
the cluster unless later Phase 3 work explicitly wires live execution.

## Configuration engine

Phase 3.4 adds Python APIs and CLI commands for `.env` parsing, preservation,
validation, derived host/URL repair, backup metadata, diff preview, and rollback.
The Bash wizard can call the Python config bridge when available and keeps its
existing Bash implementation as the production fallback during migration.

## Diagnostics engine

Phase 3.5 adds Python diagnostics collectors, route findings, image-pull
interpretation, and sanitized bundle generation. Collectors are injectable and
read-only so tests do not need a live Kubernetes cluster; production Bash
diagnostics remain available while Python diagnostics mature.

## Entry points

`./start_wizard.sh` remains the friendly command for existing users. As Python
matures, it should launch the Python guided experience rather than host new
application logic.

Clone-and-run support means contributors and operators can work from a checked
out repository without requiring `pipx`, a `.deb`, a container image, or a
single binary in Phase 3.

## State rules

Fortify Lab must infer deployed resource health from live Kubernetes and Helm
state. Local state may make the wizard friendlier, but it must not become the
authority for whether MySQL, SSC, ScanCentral, LIM, dashboard, or sample apps are
actually deployed.

Allowed local state includes selected profiles, current guided step, last failed
step, auto-advance preference, diagnostics paths, and wizard log references.

Forbidden local state includes credentials, decoded Secrets, licenses, registry
tokens, private TLS keys, database exports, and raw application logs.

## Web console posture

The companion web console is a later Phase 3 deliverable after the Python core is
solid. Remote LAN access is allowed only through explicit operator enablement,
with a generated access token and clear lab-network warnings. The console must
not show secret values by default.

## Manual test gates

Before promoting `integration/phase-3` to `dev`, manually test at least:

- guided deployment profile selection;
- smooth wait-screen behavior and auto-advance takeover;
- logs and diagnostics access while waiting;
- `.env` validation, backup, repair, and rollback paths once migrated;
- teardown and non-destructive shutdown/startup;
- route/TLS diagnostics for demo URLs;
- runbook discovery and safe execution;
- a classroom-style first-scan handoff.
