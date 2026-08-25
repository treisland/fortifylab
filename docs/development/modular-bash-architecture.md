# Retired Bash Wizard Architecture

This page is historical M7 migration context. The interactive Bash wizard modules under `scripts/wizard/` have been removed on the Python TUI migration branch. `start_wizard.sh` remains only as a compatibility shim for `--help`, `doctor`, `status`, `help topic ...`, and `config-diagnostics` through M8.

Retained Bash is limited to low-level operation adapters and host bootstrap helpers:

- app lifecycle adapters under `apps/**/start.sh`, `apps/**/stop.sh`, and `apps/**/destroy.sh`, which are referenced by `fortifylab.operations.catalog`;
- host/lab bootstrap scripts such as `scripts/create-certs.sh`, `scripts/create-secrets.sh`, and `scripts/install_microk8s.sh`;
- shared `scripts/lib/*.sh` helpers when they are used by retained lifecycle, bootstrap, or runbook scripts.

Do not add new menu, guided workflow, config editor, runbook browser, or status behavior under `scripts/wizard/`. New user-facing application behavior belongs in the root `fortifylab/` Python package and should expose clone-safe tests that avoid live Kubernetes, Helm, Docker, network, or lab requirements by default.

The old Bash wizard modules are intentionally not operation adapters. Lifecycle behavior that remains available to Python is represented by the operation catalog and executes existing app scripts directly, with previews and confirmation metadata in Python.

The deprecated Python preview package under `src/fortifylab` has also been removed on the migration branch. New application logic belongs in the root `fortifylab/` package; new compatibility behavior should be covered by clone-safe tests before it is documented.
