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

## Navigation Baseline

Pascal completed a read-only audit of the current Bash wizard navigation. M2 should use this as the parity baseline before changing interaction design.

Entrypoints to preserve or intentionally replace:

- `./start_wizard.sh` launches the interactive menu.
- `./start_wizard.sh --accept-lab-use` accepts lab-use terms, then launches the menu.
- `./start_wizard.sh doctor` runs read-only health summary.
- `./start_wizard.sh config-diagnostics` inspects `.env` host and URL wiring.
- `./start_wizard.sh apply-flight-plan <plan-id> [--yes]` stages or applies Flight Plan versions.
- `./start_wizard.sh -h|--help` prints usage.

Main menu essentials:

- `0` Initial setup and readiness.
- `1` Deploy: guided, express, resume.
- `2` Lab lifecycle controls.
- `3` Configuration editor.
- `4` Logs.
- `5` First-scan one-click demo, shown as unavailable until prerequisites are ready.
- `?` Help Center / Fortify Knowledge Center.
- `m` More tools.
- `q` Quit.

More tools preserves the full compatibility menu and numbering for docs and runbooks: setup, guided deployment, express deployment, resume or repair, Flight Plans, app management, sample apps, Dashboard access, diagnostics, advanced setup, lifecycle controls, logs, cluster snapshot, URLs and credentials, FCLI readiness, Runbook Library, configuration editor, Help Center, operational guidance, wizard log, and first-scan demo.

Workflow screens to model explicitly:

- Guided deployment profile selection, deployment mode selection, per-step controls, and completion handoff.
- Setup and readiness workflow, including guided setup steps and complete lab reset tiers.
- App lifecycle menus for MySQL, PostgreSQL, SSC, LIM, ScanCentral SAST, ScanCentral DAST, Juice Shop, WebGoat, and DVWA.
- Configuration editor, Flight Plan editor, Runbook Library, operational guidance, logs, diagnostics, and credentials views.

Architecture and TUI decisions from the audit:

- Normalize back behavior internally while preserving existing aliases: `r`, `b`, Escape, and empty Enter where historically accepted.
- Distinguish process quit from workflow return; current Bash uses `q` inconsistently.
- Decide whether number keys execute immediately or jump/highlight before Enter. The user requested jump-to-number selection, so M2 should define this deliberately.
- Treat guided deployment as a state machine, not as a simple nested menu.
- Preserve pending-change guards for Config and Flight Plan screens.
- Remove or replace the current `bin/fortifylab` Python config bridge intentionally during M1-M4.

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
| Branch upstream | Push `migration/python-tui` and track `origin/migration/python-tui` | M0 - accepted |

## Heartbeat Log

### 2026-08-25

Milestone: M0

Status: active

Changed:

- Created local `migration/python-tui` branch from `origin/dev`.
- Added the initial migration tracker and this migration document.
- Pushed `migration/python-tui` to GitHub and set upstream to `origin/migration/python-tui`.

Next:

- Commit the heartbeat update.
- Fold the navigation audit into migration docs.
- Assign Architecture and Test workstreams for M1.

Blockers: none.

Risks:

- Existing Python preview references must be audited before `src/` cleanup.
- Entrypoint policy must stay explicit as `start_wizard.sh` is replaced.
