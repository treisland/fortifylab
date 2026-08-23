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

### M3 — Deploy service + live guided deployment

Wires `services/deploy_service.py` to the existing `orchestration` DAG and
`BashOperationAdapter` so Guided deployment runs for real through the TUI for
one profile (SSC-only).

- `src/fortifylab/services/deploy_service.py` — `DeployService` builds the
  SSC-only plan (`certs` -> `secrets`/`dashboard` -> `mysql` -> `ssc`,
  filtered to steps `BashOperationAdapter` already knows how to run) and
  drives it one step at a time: `run_next(execute=False)` (the default)
  previews the next runnable step without touching the DAG, so a preview
  stays repeatable; `run_next(execute=True)` actually runs it via
  `OperationController` and commits the resulting status, unlocking
  dependents.
- `src/fortifylab/tui/screens/guided_deploy.py` — `GuidedDeployScreen`
  renders the whole plan's per-step status, is dry-run by default, and
  requires pressing `a` to arm real execution before `enter` does anything
  destructive -- the same dry-run-unless-told-otherwise posture
  `OperationCatalog`/`OperationRunner` already use elsewhere. Arming is
  one-shot: it auto-disarms after each real execution, so a stray extra
  `enter` afterward falls back to a dry-run preview instead of silently
  running the next step for real too (security review finding, fixed).
- Reachable from the main menu: select "Deploy / Resume", press `o` to
  open. `MainMenuScreen` gained a small `key -> screen factory` registry
  (`_SCREEN_FACTORIES`) so future milestones add a real screen by
  registering it, not by branching further.
- Fixed along the way: `OperationController.run(dry_run=False)` had never
  actually been exercised by any existing test (everything before M3 only
  used the dry-run path) and called `run_command()` with a keyword
  argument that didn't match its real signature -- a live TypeError on
  every real execution. Fixed, with regression tests.

There is no background/async execution here: `OperationController.run()` is
a blocking subprocess call, same as every other Bash-backed operation in
this codebase, so "live" means "the screen reflects real state after each
step returns," not a background poller. `TickEvent` is wired into the
screen (it counts ticks) but isn't load-bearing yet -- true async/parallel
execution is out of scope until a profile actually needs it.

**Done when:** `DeployService("ssc_only")` builds a validated, correctly
ordered plan; dry-run previews are repeatable and never advance the DAG;
`execute=True` runs a step for real, commits its status, and unlocks
dependents; `GuidedDeployScreen` is reachable from the main menu and starts
dry-run by default. All met in this PR.

**Known follow-up, not fixed here:** `DeployService` imports
`build_profile` from `fortifylab.tui.profiles` (deferred inside `__init__`
to avoid a circular import with `tui.screens.guided_deploy`). Code review
correctly flagged this as a services-depending-on-tui layering inversion --
`tui/profiles.py` is pure profile data with no rendering/terminal I/O, it
just historically sits in the `tui` package. The tactical deferred-import
fix is sound and covered by tests, but the real fix is relocating that
profile data to a neutral location (e.g. `fortifylab.orchestration.profiles`)
so `tui` depends on it too, not the other way around. Deferred to a
follow-up since it touches already-shipped M1/M2 modules and their tests.

### M4 — Applications, configuration, logs screens

Ports `apps_menu`, `edit_env`, `logs_menu`/`stream_logs` to `Screen`
subclasses backed by the existing `operations`/`config` packages -- no new
service layer needed for applications/configuration, since `OperationCatalog`
+ `OperationRunner` and `ConfigStore` + `envfile` already are that layer.

- `src/fortifylab/tui/screens/applications.py` — `ApplicationsScreen` lists
  start/stop for the four apps `OperationCatalog` already knows
  (`ssc`, `lim`, `mysql`, `postgresql`), dry-run by default with the same
  one-shot arm-to-execute posture as `GuidedDeployScreen`.
- `src/fortifylab/tui/screens/configuration.py` — `ConfigurationScreen`
  shows the current `.env` with secret-shaped keys redacted (reusing
  `envfile.display_value`'s existing `SECRET_KEY_RE` pattern -- not a new
  redaction rule), plus backup (unarmed, since it's additive/non-destructive)
  and rollback-to-last-backup (armed).
- `src/fortifylab/tui/screens/logs.py` + `src/fortifylab/services/logs_service.py`
  (new) — `LogsScreen` picks a component, looks up matching pods, and either
  auto-selects a single match or shows the matches to arrow-select --
  mirroring `should_skip_selection`/`matching_pods` from `operations/logs.py`,
  which the Bash `logs_menu()` already uses for the same reason. Caught and
  fixed along the way: `tui.profiles.LOG_SCOPES` values are Bash glob
  patterns (e.g. `"ssc-webapp*"`), but `matching_pods()` does a plain
  `str.startswith()` -- the literal `*` defeated every match until the glob
  suffix is stripped first.
- **Scope trim, deliberate**: destroy (`apps_menu`'s destroy action) and
  free-text `.env` value editing are **not** wired in this milestone.
  Both need typed input (an exact `DESTROY <app>` confirmation phrase, or a
  key + new value) and the TUI has no text-entry widget yet. Mapping a
  single keypress to "yes, do the destructive thing" to work around that
  would defeat the confirmation-phrase design these operations already
  have; better to leave both as Bash-wizard-only until real text entry
  exists, than to build an unsafe shortcut.

**Done when:** `ApplicationsScreen`/`ConfigurationScreen`/`LogsScreen` are
reachable from the main menu (`o` on Applications/Configuration/Logs);
applications start/stop dry-run by default and require arming; config
view never renders a secret-shaped value; logs lookup matches the Bash
wizard's skip-selection-when-one-match behavior. All met in this PR.

**Review fixes landed on top of the initial implementation:**

- Security review caught `envfile.SECRET_KEY_RE` missing `PWD`-suffixed
  keys -- `LIM_SIGNING_CERT_PWD` (a real key in `.env.example`) slipped
  through unredacted, since `ConfigurationScreen` is the first screen to
  render a live `.env`. Fixed with an underscore-aware pattern
  (`(?:^|_)PWD(?:_|$)`, not `\bPWD\b`, since `\b` doesn't create a boundary
  between an underscore and a letter).
- Code review found the `rstrip("*")` glob fix was necessary but not
  sufficient: `LOG_SCOPES` prefixes genuinely overlap once stripped
  (`sast_sensor`'s `"scancentral-sast"` is itself a prefix of
  `sast_controller`'s pods; `dast_scanner`'s `"sdast"` is a prefix of
  `dast_core`'s). Added `LogsService.matching_pods_for_scope()`, which
  excludes pods that also match a more specific sibling scope's prefix.
- Code review also found an arming footgun specific to `ApplicationsScreen`:
  unlike `GuidedDeployScreen`'s single linear "next step" target, this
  screen has many independently selectable rows, and arming was
  session-wide rather than row-scoped -- an operator could arm, arrow to a
  different row by mistake, and execute the wrong app/action for real.
  Fixed by disarming on navigation.
- The resulting duplicated arm/disarm/mode-label logic across
  `GuidedDeployScreen`, `ApplicationsScreen`, and `ConfigurationScreen` was
  factored into a shared `Armable` dataclass mixin (`tui/screens/base.py`).

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

M1 through M4, fully implemented and tested. M5-M6 are filed as tracked
GitHub issues (see below) for follow-on PRs against this runway branch —
they are not implemented here. This keeps the claim in this document
honest: an 11,000-line Bash wizard does not get ported in one PR, and
pretending otherwise would just move the risk from "still Bash" to
"untested Python."

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
