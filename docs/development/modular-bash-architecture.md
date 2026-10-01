# Modular Bash Architecture

`start_wizard.sh` is the compatibility entrypoint for the interactive lab
wizard. It owns process setup, colors, shared marks, cluster CLI detection, and
argument dispatch. Feature logic lives in modules under `scripts/wizard/`.

## Module Ownership

- `env.sh` loads `.env` and creates it from `.env.example` on first run.
- `app-registry.sh` owns component registry metadata and URL display helpers.
- `operations.sh` is a compatibility loader. Focused operations live under
  `scripts/wizard/operations/`; Flight Plan behavior lives under
  `scripts/wizard/flight-plans/`.
- `guided.sh` owns deployment profiles, guided step state, probes, wait screens,
  deployment orchestration, and preflight checks.
- `menu.sh` owns the first-time welcome flow and main menu.
- `runbooks.sh` owns Runbook Library discovery, metadata parsing, validation, parameter prompts, previews, and execution.

## Loading Contract

Top-level wizard modules are sourced from `start_wizard.sh` through
`source_wizard_module`. The operations compatibility loader owns the explicit
load order for its child modules through `source_wizard_operation_module`.
Feature modules must not source one another. Shared functions are available
after the entrypoint has completed module loading.

Keep dependency direction simple:

- entrypoint -> `scripts/lib/*` and `scripts/wizard/*`
- menus -> wizard/lib functions
- wizard modules -> shared globals and sourced library helpers
- app scripts -> app-specific deployment work

Within the operations layer, keep this direction:

```text
read-only probes and persistence -> feature operations -> orchestration -> menus
```

Menus may call operations. Operations must not open menus or collect input when
a noninteractive operation boundary is available. Cross-feature coordination
belongs in the guided/orchestration layer rather than in a low-level helper.

## Operations Modules

The compatibility loader uses dependency order, not alphabetical order:

- status and cluster-profile probes;
- application runtime and coordinated lifecycle behavior;
- focused application, license, certificate, Dashboard, and configuration UI;
- observability and credential handoff;
- environment persistence and Flight Plans;
- fcli, version discovery, environment editing, and certificate trust;
- prerequisite and advanced aggregate menus.

No child module currently exceeds 500 lines. When a module approaches that
size, split by responsibility or document why keeping the behavior together is
safer.

## Module Contract

Every sourced child module must declare comment fields named `Module`,
`Responsibility`, `Requires`, `Exports`, `Side effects`, and `Interactive` at
the top of the file. For example, the module value may be
`operations/example`, followed by one concise ownership statement, its runtime
dependencies, public functions, possible mutations, and whether it prompts.

Each module must also have an idempotent source guard. Sourcing a module must
define functions only: it must not execute an operation, prompt, call `exit`,
change global shell error modes, or install a global trap.

## Contributor Rules

- Put a new function in the module that owns its responsibility. Do not grow
  the compatibility loader with feature logic.
- Keep read-only probes separate from mutations and name both explicitly.
- Keep operator input and rendering in menu functions; make the underlying
  operation callable without a TTY.
- Return a status to the caller instead of exiting the wizard from a helper.
- Declare local variables and quote expansions unless documented splitting is
  intentional. Use arrays for command arguments and do not introduce `eval`.
- Route structured configuration and dependency-graph logic toward
  `src/fortifylab/`; Bash remains the compatibility and command-execution
  surface.
- Preserve secret boundaries: never place credentials in output, logs, process
  arguments, filenames, or persisted wizard state.
- Dependencies that must survive wizard termination or a host restart must be
  represented in Kubernetes, not only as Bash sequencing.
- Separate mechanical extraction from behavior changes so each PR remains
  reviewable and independently revertible.

## Naming

Use prefixes for new functions so future modules do not collide:

- `ui_` for reusable user-interface helpers
- `env_` for `.env` parsing, edits, backups, and repair
- `k8s_` for Kubernetes and Helm helpers
- `guided_` for guided deployment state and orchestration
- `lab_lifecycle_` for start, shutdown, and destroy workflows
- `credential_` for credential handoff helpers

Avoid generic function names such as `run`, `status`, `render`, or `check`.

## Error Handling

Helper functions should return `0` for success and nonzero for failure. Prefer
`error` for user-facing failures and `wizard_log_event` for operational detail.
Avoid `exit` inside helpers unless the current process cannot continue.

## Python Migration Bridge

Phase 3 keeps this modular Bash layout as the compatibility surface while new
application behavior moves into Python. `start_wizard.sh` should stay small and
continue loading Bash modules until it can launch the Python guided experience
without breaking existing clone-and-run workflows.

New application logic should prefer `src/fortifylab/`. Bash modules may call
Python commands only when the Python behavior has tests and preserves the
operator-facing exit behavior, messages, and safety boundaries.

## Validation

Before opening a PR for wizard changes, run:

```bash
bash scripts/validate-bash-modules.sh
bash -n start_wizard.sh scripts/wizard/*.sh \
  scripts/wizard/operations/*.sh scripts/wizard/flight-plans/*.sh \
  scripts/lib/*.sh
python3 -m unittest tests.test_operations_modularity
python3 -m unittest tests.test_guided_wizard tests.test_wizard_contract \
  tests.test_flight_plans
```

Run the broader test suite when a change touches docs, lifecycle behavior,
Kubernetes object contracts, or user-facing help.
