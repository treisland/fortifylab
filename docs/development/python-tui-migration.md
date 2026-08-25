# Python TUI Migration

Fortify Lab is migrating from the current Bash wizard to a maintainable Python
CLI/TUI application. The new application must preserve the existing navigation
structure and lab operation behavior while making the repo easier for future
maintainers to understand, test, and extend.

This is not a web UI effort. Fortify Lab remains a CLI-first lab management tool,
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

M2 menu model contract:

- Menu data lives in `fortifylab/navigation/models.py`, `baseline.py`, and `registry.py`.
- Number keys are modeled as jump-highlight selection; Enter/Return activates the selected item.
- Duplicate numbers are scoped by `MenuNode.id`, so `main:1`, `more_tools:1`, and `guided_deployment:1` can point to different targets.
- Back and return aliases are metadata on screens and return items: `r`, `b`, Escape, and empty Enter are preserved where the Bash baseline accepted them.
- Disabled entries keep `disabled_reason` text on the item; the first-scan demo is unavailable until prerequisites are ready.
- Placeholder targets use stable `ActionRef` values until M3-M6 replace them with real operations, config, diagnostics, and runbook views.
- Guided deployment is represented as a `workflow_boundary` screen for profile selection, deployment mode selection, per-step controls, and completion handoff.

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

## Test Strategy

M1 tests live in `tests/test_m1_entrypoints.py` and cover only clone-safe
entrypoint behavior:

- `./bin/fortifylab --help`;
- `./bin/fortifylab tui --smoke-test`;
- import sanity from the repo root Python package;
- `start_wizard.sh` removed or reduced to a deliberate shim.

The noninteractive TUI launch contract for Architecture is
`./bin/fortifylab tui --smoke-test`. It should print deterministic placeholder
output identifying the Fortify Lab TUI and M1 placeholder/skeleton state, then
exit `0` without reading terminal input.

Deprecated `tests/test_python_*.py` files have been moved to
`tests/quarantine/python_preview/` with default-discovery-safe filenames. The
quarantine README classifies each file as keep, rewrite, quarantine, or delete
for later milestones. These old preview contracts should not block M1 unless
Architecture intentionally adopts the behavior.

## Decision Log

| Date | Decision | Status |
| --- | --- | --- |
| 2026-08-25 | Use `migration/python-tui` as the migration integration branch created from current `dev`. | Accepted |
| 2026-08-25 | Fortify Lab remains CLI/TUI focused; no web UI will be built. | Accepted |
| 2026-08-25 | Preserve current navigation structure before improving interaction design. | Accepted |
| 2026-08-25 | Treat current `src/` as deprecated preview code to replace intentionally. | Accepted |
| 2026-08-25 | Keep Bash deployment scripts as temporary operation adapters in early milestones. | Accepted |
| 2026-08-25 | Use Textual as the interactive TUI framework starting in M2. M1 remains standard-library only for clone-and-run entrypoint checks. | Accepted |
| 2026-08-25 | `./bin/fortifylab` is the primary Python application entrypoint. `./start_wizard.sh` is a compatibility shim during migration. | Accepted |
| 2026-08-25 | The new root-level `fortifylab/` package is the intentional migration target. Deprecated preview code under `src/` remains in-tree until cleanup is handled deliberately. | Accepted |

## Open Decisions

| Decision | Recommendation | Needed By |
| --- | --- | --- |
| TUI framework | Textual | M1 - accepted |
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

### 2026-08-25

Milestone: M1

Workstream: Architecture

Branch: `agent/architecture-M1-skeleton`

Status: complete

Changed:

- Added the intentional root-level Python package skeleton at `fortifylab/`.
- Pointed `./bin/fortifylab` at the new package instead of deprecated `src/`.
- Converted `./start_wizard.sh` into a deliberate compatibility shim.
- Accepted Textual as the M2 TUI framework while keeping M1 standard-library only.
- Defined the noninteractive TUI test contract: `./bin/fortifylab tui --smoke-test`, `./bin/fortifylab tui --check`, or `FORTIFYLAB_TUI_TEST_MODE=1`.
- Merged Architecture PR #451 into `migration/python-tui`.

Next:

- Update Test PR #450 against the merged skeleton.

Blockers: none.

Risks:

- Deprecated `src/` preview code remains in-tree until references, tests, and docs are migrated or removed intentionally.
- Legacy Bash wizard subcommands are not reimplemented in M1.

### 2026-08-25

Milestone: M1

Workstream: Tests

Branch: `agent/test-M1-entrypoints`

Status: complete

Changed:

- Merged the Architecture skeleton into the Test branch.
- Added clone-safe M1 entrypoint acceptance tests.
- Defined the noninteractive TUI launch contract as `./bin/fortifylab tui --smoke-test`.
- Quarantined deprecated Python preview tests outside default discovery.
- Quarantined retired Bash wizard internal tests outside default discovery.
- Documented quarantine rationale in `tests/quarantine/python_preview/README.md` and `tests/quarantine/bash_wizard_internal/README.md`.
- Merged Test PR #450 into `migration/python-tui`.

Acceptance evidence:

- `./bin/fortifylab --help` passed during Architecture review.
- `./bin/fortifylab tui --smoke-test` passed during Architecture review.
- `./bin/fortifylab tui --check` passed during Architecture and Test review.
- `python3 -m compileall -q fortifylab` passed during Architecture and Test review.
- `python3 -m unittest tests.test_m1_entrypoints -v` passed.
- `python3 -m unittest discover -s tests -v` passed with 81 tests.
- `./scripts/validate-docs.sh` passed documentation quality gates in CI.

Next:

- Close M1 in the PM tracker.
- Open M2 navigation parity workstreams.

Blockers: none.

Risks:

- Behavior-level coverage from quarantined tests must be reintroduced milestone by milestone as supported Python CLI/TUI behavior lands.


### 2026-08-25

Milestone: M2

Workstream: PM

Branch: `agent/pm-M1-closeout-open-M2`

Status: active

Changed:

- PM gate review accepted M1 as complete.
- Updated the tracker to set `current_milestone: M2`.
- Cleared obsolete M1 skeleton blockers.
- Opened M2 navigation parity as the next milestone.

Next:

- Merge this closeout branch into `migration/python-tui`.
- Spawn Navigation Model on `agent/navigation-M2-menu-model`.
- Spawn M2 Test on `agent/test-M2-menu-parity`.
- Start TUI keybinding implementation on `agent/tui-M2-keybindings` after the menu model contract is visible, or with close coordination.

Blockers: none.

Risks:

- M2 must preserve the documented Bash wizard navigation before improving flow design.
- No mutating operation wiring belongs in M2; that is M3.

### 2026-08-25

Milestone: M2

Workstream: Navigation

Branch: `agent/navigation-M2-menu-model`

Status: complete

Changed:

- Added the first Python menu model contract for the documented Bash wizard baseline.
- Exposed deterministic helpers for menu keys, labels, lookup, disabled reasons, aliases, and workflow boundaries.
- Merged Navigation Model PR #454 into `migration/python-tui`.

Next:

- Coordinate with Test and TUI agents now that the model contract is available.

Blockers: none.

Risks:

- This is intentionally a model contract only; no operation execution, config editor, diagnostics, or runbook behavior is wired yet.

### 2026-08-25

Milestone: M2

Workstream: Test

Branch: `agent/test-M2-menu-parity`

Status: complete

Changed:

- Added noninteractive M2 contract tests for menu labels, ordering, action types, number jumps, arrow selection, Enter activation, normalized back/help/quit keys, and disabled reason text.
- Defined the expected test API around `fortifylab.navigation` and `fortifylab.navigation.controller`.
- Merged M2 Test PR #453 into `migration/python-tui`.

Next:

- Carry the same noninteractive testing style into M3 operation adapter tests.

Blockers: none.

Risks:

- M3 tests must avoid real Kubernetes, Helm, Docker, or network dependencies.

### 2026-08-25

Milestone: M2

Workstream: TUI

Branch: `agent/tui-M2-keybindings`

Status: complete

Changed:

- Added `fortifylab.navigation.controller` with pure, noninteractive key handling.
- Activated the M2 keyhandling tests for arrow movement, jump-to-number selection, Enter activation, disabled selections, multi-digit jumps, and normalized back/help/quit keys.
- Replaced the M1 placeholder shell with a Textual-backed TUI that renders the shared navigation model.
- Kept `./bin/fortifylab tui --check` deterministic and safe for environments without an interactive terminal.
- Merged TUI Keybindings PR #455 into `migration/python-tui`.

Acceptance evidence:

- `python3 -m compileall -q fortifylab` passed.
- `python3 -m unittest tests.test_m2_menu_parity -v` passed with 10 tests.
- `./bin/fortifylab tui --check` passed and prints the M2 menu.
- `python3 -m unittest discover -s tests -v` passed with 99 tests.
- PR #455 `offline-docs` CI passed before merge.

Next:

- Close M2 in the PM tracker.
- Open M3 operation adapter workstreams.

Blockers: none.

Risks:

- Interactive operations remain placeholders until M3 operation adapters land.
- Full interactive Textual mode requires dependencies from `requirements-python.txt`; noninteractive checks do not.


### 2026-08-25

Milestone: M3

Workstream: PM

Branch: `agent/pm-M2-closeout-open-M3`

Status: active

Changed:

- PM gate review accepted M2 as complete.
- Updated the tracker to set `current_milestone: M3`.
- Recorded Navigation Model PR #454, M2 Test PR #453, and TUI Keybindings PR #455 as M2 completion evidence.
- Opened M3 operation adapter work as the next milestone.

Next:

- Merge this closeout branch into `migration/python-tui`.
- Spawn Operations Adapter on `agent/operations-M3-adapter-catalog`.
- Spawn M3 Test on `agent/test-M3-operation-adapters`.
- Spawn Config Design on `agent/config-M4-schema-design` as read-mostly foundation work.

Blockers: none.

Risks:

- M3 must not execute mutating operations without explicit confirmation gates.
- Config implementation should wait for operation runner boundaries before replacing editor behavior.

### 2026-08-25

Milestone: M3

Workstream: Tests

Branch: `agent/test-M3-operation-adapters`

Status: active

Changed:

- Added noninteractive operation adapter contract tests for stable operation IDs, command plan shape, dry-run previews, mutating confirmation gates, mocked execution success/failure, stdout/stderr/result modeling, and secret redaction.
- Kept the tests dependency-skipped until the M3 operations implementation exposes the agreed `fortifylab.operations` API.

Verification:

- `python3 -m unittest tests.test_m3_operation_adapters -v` passed with 6 skips.
- `python3 -m unittest discover -s tests -v` passed with 105 tests and 6 skips.

Next:

- Re-run this suite after `agent/operations-M3-adapter-catalog` lands; the contract tests should activate automatically.

Blockers:

- Waiting on `fortifylab.operations` to expose `OperationCatalog`, `OperationRunner`, `CommandResult`, `OperationImpact`, and `redact_text`.

Risks:

- Tests intentionally make no Kubernetes, Helm, Docker, network, or mutating command calls; implementation branches must preserve that boundary in CI.
