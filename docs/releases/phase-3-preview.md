# Phase 3 preview release notes

Phase 3 migrates Fortify Lab from a Bash-centered wizard toward a Python
application while preserving existing clone-and-run workflows.

Integrated preview areas:

- Python CLI foundation and command wrapper.
- Guided deployment TUI data model and smooth-rendering prototype.
- Deployment orchestration model with resumable session metadata.
- `.env` parsing, validation, backup, rollback, and derived URL repair APIs.
- Structured diagnostics collectors, route checks, registry findings, and
  sanitized bundle generation.
- Operation command layer for certs, secrets, app lifecycle, logs, and runbooks.
- Local/LAN companion web console scaffold with token-required LAN mode.
- Bootstrap, environment, compatibility wrapper, and promotion gate checks.

Compatibility notes:

- `./start_wizard.sh` remains the production guided deployment entrypoint.
- `./bin/fortifylab` is the Phase 3 Python preview entrypoint.
- Python commands are intentionally stdlib-only in this phase.
- Mutating Python operation commands dry-run unless explicit execution is
  requested.
