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

`agent/phase-3.11-interactive-operator-console` is the active CLI/TUI-focused Python migration branch. It starts from current `dev` after the accepted Phase 3.7-3.10 console foundation and makes the operator menu operational.

`dev` and `main` stay untouched until manual testing accepts each Phase 3 branch.

Promotion flow:

```text
agent/phase-3.x-* -> dev -> main
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
8. Packaging and upgrade hardening after the CLI/TUI path is stable.

## Phase 3.7 direction reset

Phase 3.7 locks the migration back onto a terminal-first operator console. It
keeps the Python runtime focused on CLI/TUI deployment, configuration,
diagnostics, runbooks, logs, certificates, and lifecycle workflows. Fortify Lab
will not grow a replacement web console in this runway; browser-based cluster
views remain the Kubernetes Dashboard's job, and Fortify product UIs remain the
application-facing surfaces.

This phase also records the compatibility boundary: Bash remains the production guided wizard through `./start_wizard.sh` until the Python guided experience reaches parity. New application logic should land in Python when practical, while proven Bash scripts remain execution adapters and recovery tools.

## Phase 3.8 dependency foundation

Phase 3.8 introduces a conservative Python runtime dependency posture without
breaking clone-and-run behavior. The existing `./bin/fortifylab` wrapper and
preview commands continue to run from source with the Python standard library.
Richer Python CLI/TUI work can install the explicit runtime dependency file:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-python.txt
```

The intended runtime stack is:

- Typer for typed CLI command structure;
- Rich for terminal tables, colors, panels, progress, and plain-mode output;
- Pydantic for typed configuration, runbook, diagnostic, operation, and state
  contracts;
- Textual for the full interactive TUI once the menu shell needs panes, forms,
  and live refresh.

These dependencies are separated from `requirements-docs.txt`. Documentation
build dependencies do not become lab runtime dependencies, and optional TUI
features must explain missing dependency installation steps clearly.

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

## Operation command layer

Phase 3.6 adds Python operation descriptors for certificates, secrets, app
lifecycle scripts, pod logs, and safe runbook previews. Mutating operations are
dry-run by default and require explicit execution, which lets later work replace
Bash operation internals incrementally without surprising operators.

## Interactive operator console

Phase 3.11 turns `./bin/fortifylab menu` from a render-only preview into an
interactive terminal entry point. Operators can select numbered workspaces for
the live dashboard, configuration, logs, diagnostics, runbooks, certificates,
tools, and help. `./bin/fortifylab menu --preview` remains available for tests,
documentation, and non-interactive rendering.

The menu does not silently mutate the lab. Read-only Python screens run directly,
while deployment, application lifecycle, certificate, and wizard handoffs show
the command and ask for confirmation before calling existing Bash scripts. This
keeps the CLI focused and useful now without pretending the Python guided
deployment engine has already replaced the Bash implementation.

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

## CLI/TUI posture

Fortify Lab remains a CLI/TUI-first operator. The Python runtime should improve
guided deployment, configuration, diagnostics, runbooks, operation commands,
metrics summaries, and dashboard-style terminal views without becoming a
replacement for Kubernetes-native operator consoles. Browser-based Fortify Lab management is out of scope for this Phase 3 integration.

The mature menu direction is task-oriented rather than script-oriented:
Dashboard, Deploy / Resume, Applications, Configuration, Runbooks, Logs,
Diagnostics, Certificates & Trust, Tools, and Help. Phase 3.11 makes that menu
interactive and useful while keeping live deployment mutation behind explicit
Bash handoffs until native Python replacements reach parity.

## Manual test gates

Before promoting `agent/phase-3.7-3.10-python-cli-tui` to `dev`, manually test at least:

- guided deployment profile selection;
- smooth wait-screen behavior and auto-advance takeover;
- logs and diagnostics access while waiting;
- `.env` validation, backup, repair, and rollback paths once migrated;
- teardown and non-destructive shutdown/startup;
- route/TLS diagnostics for demo URLs;
- runbook discovery and safe execution;
- a classroom-style first-scan handoff.
