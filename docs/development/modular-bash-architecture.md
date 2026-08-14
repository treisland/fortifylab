# Modular Bash Architecture

`start_wizard.sh` is the compatibility entrypoint for the interactive lab
wizard. It owns process setup, colors, shared marks, cluster CLI detection, and
argument dispatch. Feature logic lives in modules under `scripts/wizard/`.

## Module Ownership

- `env.sh` loads `.env` and creates it from `.env.example` on first run.
- `app-registry.sh` owns component registry metadata and URL display helpers.
- `operations.sh` owns status rendering, app lifecycle, logs, credentials,
  configuration, diagnostics, FCLI, and prerequisite helpers.
- `guided.sh` owns deployment profiles, guided step state, probes, wait screens,
  deployment orchestration, and preflight checks.
- `menu.sh` owns the first-time welcome flow and main menu.
- `runbooks.sh` owns Runbook Library discovery, metadata parsing, validation, parameter prompts, previews, and execution.

## Loading Contract

All wizard modules are sourced from `start_wizard.sh` through
`source_wizard_module`. Do not source wizard modules from each other. Shared
functions should be available after the entrypoint has loaded every module.

Keep dependency direction simple:

- entrypoint -> `scripts/lib/*` and `scripts/wizard/*`
- menus -> wizard/lib functions
- wizard modules -> shared globals and sourced library helpers
- app scripts -> app-specific deployment work

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

## Validation

Before opening a PR for wizard changes, run:

```bash
bash -n start_wizard.sh scripts/wizard/*.sh scripts/lib/*.sh
python3 -m unittest tests.test_guided_wizard tests.test_wizard_contract
```

Run the broader test suite when a change touches docs, lifecycle behavior,
Kubernetes object contracts, or user-facing help.
