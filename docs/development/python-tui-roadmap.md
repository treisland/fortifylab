# Python TUI migration roadmap

This is the implementation roadmap for finishing the work described in
[Phase 3 Python migration](phase-3-python-migration.md) and
[ADR 0002](../adr/0002-python-runtime-migration.md): replacing the
`scripts/wizard/*.sh` menu system with an interactive Python TUI, without a
big-bang rewrite and without breaking `./start_wizard.sh` at any point along
the way.

It exists to answer three questions concretely, where the two documents above
stay at the policy level:

- What ships in which order.
- What "done" means for each slice.
- Where GitHub issues track each slice, so status doesn't live only in this
  file.

## Ground rules (inherited, not new)

- `./start_wizard.sh` keeps working, unmodified in behavior, until a Python
  screen has reached parity with the Bash menu it replaces.
- Bash scripts stay as execution adapters (`BashOperationAdapter`) for
  anything not yet ported; nothing in `apps/*/*.sh` or `scripts/*.sh` is
  deleted as part of a slice, only stopped being the primary path once its
  Python replacement has a passing test suite and a manual parity check.
- Local Python state stores only wizard/session metadata (profile, current
  step, auto-advance preference, log/diagnostics paths) — never credentials,
  decoded Secrets, license contents, or tokens. Same rule as ADR 0002.
- Every milestone below lands as its own PR into this runway branch
  (`agent/phase-3.7-3.10-python-cli-tui`), reviewed independently. The runway
  branch is what eventually goes to `dev`.

## Milestones

### M1 — Domain extraction (foundation)

Pure, testable Python modules for logic that today lives only in Bash or as a
standalone script, with no behavior change to the running wizard.

- `src/fortifylab/domain/scan_types.py` — a `ScanType` protocol matching the
  strategy shape `scan-demo.sh` already documents in its own header comment
  (`prereqs`, `login`, `sensor_check`, `package`, `submit`, `poll`, `results`,
  `logout`), plus a `SastIwaJavaScan` implementation mirroring the existing
  Bash flow.
- `src/fortifylab/domain/flight_plans.py` — `Catalog`/`FlightPlan` dataclasses
  ported from `scripts/tools/flight-plans.py` (currently a flat script, not
  part of the package).
- `src/fortifylab/services/flight_plan_service.py` — read-only Flight Plan
  queries a screen needs (listing plans, comparing the current `.env`
  against a plan, natural-sort version comparison), separated from the
  catalog model. Docker Hub/registry discovery itself stays in
  `scripts/tools/flight-plans.py` for now — it isn't ported here.

**Done when:** unit tests cover catalog loading, version comparison, and the
scan-type protocol dispatch, with no changes to `scripts/wizard/*.sh` or
`scripts/tools/flight-plans.py` behavior (the CLI script keeps working
standalone during the transition).

### M2 — Interactive TUI framework

Replaces the static `render_operator_menu()` preview with a real event loop,
and replaces the Bash `while true; case $choice` menu nesting with a screen
stack.

- `src/fortifylab/tui/events.py` — `KeyEvent` / `TickEvent` / `ResizeEvent`.
- `src/fortifylab/tui/input.py` — raw-mode terminal reader producing events.
- `src/fortifylab/tui/router.py` — screen stack (`push` / `pop` / `replace`).
- `src/fortifylab/tui/screens/base.py` — `Screen` ABC (`render()`,
  `handle_event()`, `on_enter()` / `on_exit()`).
- `src/fortifylab/tui/screens/main_menu.py` — first real screen, ported from
  `scripts/wizard/menu.sh`'s `main_menu()`, reachable via
  `./bin/fortifylab tui --interactive` (the plain `tui` subcommand still
  renders the static preview; `--demo-screen` still renders the guided-step
  prototype).
- `src/fortifylab/app.py` — composition root for the TUI process only:
  builds the `TerminalScreen` output adapter and starts the `Router` on
  `MainMenuScreen`. It does not yet construct `ConfigStore`,
  `OperationRunner`, `ClusterCollector`, or any other live service — that
  wiring lands with M3+ as each screen needs it.

**Done when:** `./bin/fortifylab tui --interactive` opens a real interactive
main menu (arrow keys or number keys, quit, help) rendered through
`TerminalScreen`, backed by the same static `OPERATOR_MENU` descriptions as
today's preview (not live `ConfigStore`/dashboard data yet), with no
destructive actions wired yet (navigation only — selecting an item shows its
description as a preview, matching today's `deploy --plan` behavior, not a
live run).

### M3 — Deploy service + live guided deployment (tracked, not in this PR)

Wire `services/deploy_service.py` to the existing `orchestration` DAG and
`BashOperationAdapter` so Guided deployment runs for real through the TUI for
one profile (SSC-only) end-to-end, with live status feeding the screen via
`TickEvent`.

### M4 — Applications, configuration, logs screens (tracked, not in this PR)

Port `apps_menu`, `edit_env`, `logs_menu`/`stream_logs` to `Screen`
subclasses backed by the existing `operations`/`config` packages.

### M5 — Diagnostics, runbooks, help, fcli/trust lifecycle (tracked, not in this PR)

Port `live_status`, `runbooks_menu`, `help_center`, and the fcli
activation/trust-import lifecycle (`domain/fcli.py`) once the Bash fcli flow
in `operations.sh` stabilizes (it's the most actively bug-fixed area on `dev`
right now — deliberately last so the port isn't chasing a moving target).

### M6 — Cutover readiness (tracked, not in this PR)

`start_wizard.sh` launches the Python TUI once M2-M5 reach parity; manual
test gates from `phase-3-python-migration.md` re-run before promoting the
runway branch to `dev`.

## What this PR actually delivers

M1 and M2, fully implemented and tested. M3-M6 are filed as tracked GitHub
issues (see below) for follow-on PRs against this runway branch — they are
not implemented here. This keeps the claim in this document honest: an
11,000-line Bash wizard does not get ported in one PR, and pretending
otherwise would just move the risk from "still Bash" to "untested Python."

## Issue tracking

Each milestone above has a corresponding GitHub issue under parent tracking
issue [#437](https://github.com/treisland/fortifylab/issues/437) on
`treisland/fortifylab`, labeled `python-tui-migration`:

- [#438](https://github.com/treisland/fortifylab/issues/438) — M1: Domain extraction
- [#439](https://github.com/treisland/fortifylab/issues/439) — M2: Interactive TUI framework + main menu screen
- [#440](https://github.com/treisland/fortifylab/issues/440) — M3: Deploy service + live guided deployment
- [#441](https://github.com/treisland/fortifylab/issues/441) — M4: Applications, configuration, logs screens
- [#442](https://github.com/treisland/fortifylab/issues/442) — M5: Diagnostics, runbooks, help, fcli/trust lifecycle
- [#443](https://github.com/treisland/fortifylab/issues/443) — M6: Cutover readiness

The parent issue lists all six and is the place to check current status; this
document is the place to check *scope and acceptance criteria* for each one.
