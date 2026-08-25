# Python TUI Migration

FortifyLab is migrating from the current Bash wizard to a maintainable Python
CLI/TUI application. The new application must preserve the existing navigation
structure and lab operation behavior while making the repo easier for future
maintainers to understand, test, and extend.

This is not a web UI effort. FortifyLab remains a CLI-first lab management tool,
with a terminal user interface as the target interactive experience.

## Objective

Replace the monolithic Bash wizard with a structured Python application that
owns:

- navigation and user interaction;
- config parsing, validation, backups, diffs, and repair;
- status checks and diagnostics;
- command previews, confirmations, execution results, and logging;
- runbook discovery and help workflows.

Existing Bash deployment scripts may remain as temporary operation adapters
while the Python application layer is introduced. Port individual Bash
operations only when doing so improves safety, testability, or maintainability.

## Branch Model

The migration branch is the shared integration branch for this effort:

```text
dev
  -> migration/python-tui
       -> agent/<workstream>-<milestone>-<short-topic>
```

All focused migration PRs target `migration/python-tui`. The migration branch
will merge back to `dev` after the milestone gates are complete.

## Source Of Truth

Two files track the effort:

- `.migration/python-tui-plan.yml` stores machine-readable milestone,
  workstream, blocker, risk, and heartbeat state.
- `docs/development/python-tui-migration.md` stores the human-readable project
  context, decision log, milestone notes, and heartbeat log.

Every PR that changes project status, scope, blockers, or risks should update
the tracker.

## Milestones

| Milestone | Focus | Gate |
| --- | --- | --- |
| M0 | Migration branch and project controls | Branch, tracker, docs, heartbeats, and risks exist |
| M1 | Python app skeleton and entrypoints | `./bin/fortifylab --help` and placeholder TUI work |
| M2 | Navigation parity | Python menu mirrors Bash wizard with arrows and number jumps |
| M3 | Operation adapters | Existing Bash scripts run through safe Python operation catalog |
| M4 | Python-native config editor | `.env` editing, validation, backup, diff, and repair work |
| M5 | Status and diagnostics | Doctor/status/diagnostic bundle behavior works without Bash wizard |
| M6 | Runbooks and help | Runbook library and help topics are available in the TUI |
| M7 | Bash wizard retirement | `start_wizard.sh` is retired or reduced to an intentional shim |
| M8 | Merge back to dev | All gates pass and maintainer docs describe the final architecture |

## Workstreams

The PM workstream owns coordination, milestone gates, heartbeats, branch rules,
and blocker tracking.

Specialist workstreams should stay narrow:

- Architecture: package layout, entrypoints, module boundaries, and migration
  contracts.
- Navigation: current Bash menu audit and Python navigation model.
- TUI: terminal framework, keybindings, screens, and interaction polish.
- Operations: operation catalog, Bash adapters, dry-run mode, confirmations,
  output streaming, and redaction.
- Config: `.env` schema, parser, writer, validation, backup, diff, repair, and
  secret redaction.
- Diagnostics: prerequisite, license, cluster, pod, registry, TLS, doctor, and
  bundle checks.
- Tests: entrypoints, menu parity, operation plans, config mutation, redaction,
  and milestone acceptance.
- Docs: README, development docs, getting started, and stale migration language.

M1 and M2 should be mostly sequential. After the package skeleton and navigation
model are stable, config, operations, diagnostics, tests, and docs can proceed
concurrently.

## Heartbeat Ritual

Every active workstream reports:

```text
Date:
Milestone:
Workstream:
Branch:
Status: on_track | blocked | stale | complete
Changed:
Next:
Blockers:
Risks:
Needs PM/User Decision:
```

Cadence:

- daily while migration is active;
- per PR when work materially changes;
- at every milestone gate;
- immediately when blocked;
- stale after three days without a heartbeat.

## Initial Risks

- The current `src/` directory is deprecated in direction but still has tests,
  docs, and Bash bridge call sites. It must be intentionally replaced or
  migrated, not blindly deleted.
- `start_wizard.sh` is currently the production interactive entrypoint. Replacing
  it requires a clear compatibility decision.
- The first TUI release should avoid rewriting every Helm/Kubernetes operation.
  Keep Bash operation adapters until Python ports have clear value and tests.

## Decision Log

| Date | Decision | Status |
| --- | --- | --- |
| 2026-08-25 | Use `migration/python-tui` as the migration integration branch created from current `dev`. | Accepted |
| 2026-08-25 | FortifyLab remains CLI/TUI focused; no web UI will be built. | Accepted |
| 2026-08-25 | Preserve current navigation structure before improving interaction design. | Accepted |
| 2026-08-25 | Treat current `src/` as deprecated preview code to replace intentionally. | Accepted |
| 2026-08-25 | Keep Bash deployment scripts as temporary operation adapters in early milestones. | Accepted |
| 2026-08-25 | Use Textual as the recommended TUI framework unless M1 discovers a blocking constraint. | Proposed |

## Open Decisions

| Decision | Recommendation | Needed By |
| --- | --- | --- |
| TUI framework | Textual | M1 |
| Branch upstream | Push `migration/python-tui` and track `origin/migration/python-tui` | M0 |

## Heartbeat Log

### 2026-08-25

Milestone: M0

Status: active

Changed:

- Created local `migration/python-tui` branch from `origin/dev`.
- Added the initial migration tracker and this migration document.

Next:

- Review and commit M0 project-control files.
- Push `migration/python-tui`.
- Assign Architecture and Navigation audit workstreams.

Blockers: none.

Risks:

- Existing Python preview references must be audited before `src/` cleanup.
- Entrypoint policy must stay explicit as `start_wizard.sh` is replaced.
