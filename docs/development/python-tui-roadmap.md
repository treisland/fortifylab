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

### M5 — Diagnostics, runbooks, help screens

Ports `live_status`, `runbooks_menu`, and `help_center` -- each backed by an
existing, already-safe module, so this milestone is mostly wiring rather
than new logic:

- `src/fortifylab/tui/screens/diagnostics.py` — `DiagnosticsScreen` runs
  the existing `ClusterCollector` (already read-only and injectable,
  unchanged) and can write a sanitized diagnostics bundle from the
  collected results via the existing `diagnostics.write_bundle`
  (sanitization was already built in; this milestone just feeds it real
  collector output instead of the CLI's static placeholder text).
- `src/fortifylab/tui/screens/runbooks.py` — `RunbooksScreen` lists the
  three topics `OperationCatalog.runbook()` already knows
  (`first-scan`, `backup`, `troubleshooting`) and previews them via the
  existing safe `sed`-excerpt operation. Read-only, no arming concept at
  all -- there's nothing to execute.
- `src/fortifylab/domain/help_center.py` (new) + `src/fortifylab/tui/screens/help.py`
  — `HelpScreen` ports the topic table from `scripts/lib/help.sh`'s
  `HELP_TOPIC_ID`/`HELP_TOPIC_LABEL`/`HELP_TOPIC_FILE` arrays (only the 13
  topics `help_center()`'s own interactive menu actually lists -- the
  Bash script's `guided/*`/`troubleshooting/*` alias IDs are used by
  *other* flows for contextual help, not this menu) and renders the same
  committed, offline `docs/help/*.txt` files the Bash version reads. No
  new help content was written; this is a loader for existing text.

**Deliberately not in this milestone**: the fcli activation/trust-import
lifecycle (`domain/fcli.py`). It remains the most actively bug-fixed area
on `dev` (see the M5 rationale this replaces below) -- porting it now would
mean chasing a moving target. Left for a dedicated follow-up once that
Bash flow settles; not tracked under a numbered milestone here since it
doesn't block M6 cutover readiness the way M1-M5 do.

**Done when:** `DiagnosticsScreen`/`RunbooksScreen`/`HelpScreen` are
reachable from the main menu (`o` on Diagnostics/Runbooks/Help);
diagnostics collection and bundle writing use real collector output;
runbook previews match `OperationCatalog.runbook()`'s existing three
topics; every listed help topic loads its real, committed `docs/help/*.txt`
content. All met in this PR.

**Review fixes landed on top of the initial implementation:**

- Code review caught an uncaught `OSError` crashing the TUI on a bundle-write
  failure in `DiagnosticsScreen._write_bundle` (e.g. a blocked/unwritable
  path) -- now caught and shown as a fail-styled message, matching every
  other screen's "surface the error, don't crash the event loop" posture.
- Security review flagged `diagnostics.sanitize_text()`'s keyword/line-based
  redaction as a thin guard now that a screen persists collector output to
  disk for the first time (M4's `LogsScreen` only ever rendered
  transiently). Not exploitable today -- `ClusterCollector` only runs
  `get`-style read commands, none of which surface Secret values -- but
  flagged as something to revisit structurally (not just by widening the
  keyword list) before any future collector reads `-o yaml`, `describe`,
  or configmap/secret contents.
- Documentation review confirmed the fcli-exclusion claim is literally true
  (no fcli code anywhere in the diff) and the 13-topic Help Center
  transcription is exact against `scripts/lib/help.sh`, and posted a
  clarifying comment on #442 since its original scope bundled the fcli
  lifecycle in with M5.

### M6 — Cutover readiness

This milestone's own gate, stated plainly in its original scope, is
**"once M2-M5 reach parity."** They have not, and this PR does not pretend
otherwise. Concretely: `scripts/wizard/menu.sh`'s "More tools" menu has 22
actions (`setup_menu`, `guided_deployment_menu`, `deploy_from_scratch`,
`resume_repair`, `versions_menu`, `apps_menu`, `sample_apps_menu`,
`dashboard_access_menu`, `live_status`, `advanced_menu`,
`lab_lifecycle_menu`, `stream_logs`, `cluster_status`, `logs_menu`,
`urls_creds`, `fcli_tools_menu`, `runbooks_menu`, `edit_env`,
`help_center`, `operational_guidance_menu`, `wizard_log_viewer`,
`scan_demo_menu`). Roughly seven of those have any Python screen behind
them today (deploy, applications, logs, diagnostics/live-status,
runbooks, configuration/edit-env, help), and every one of those seven is
narrower than its Bash counterpart: one deployment profile, not a picker;
four apps, not the full app registry; view + backup/rollback, not a full
`.env` editor; no destroy anywhere. Fifteen actions -- including the
Flight Plan version manager, sample apps, dashboard access, host-level
setup, lab lifecycle controls, URLs/credentials, fcli readiness, and the
first-scan demo -- have no Python screen at all. Making `start_wizard.sh`
launch the Python TUI *by default* at this point would be a real
regression for every operator who relies on those fifteen actions, and
would directly violate this repo's own compatibility rule (ADR 0002:
`start_wizard.sh` "continues to start the normal guided workflow"; this
roadmap's own ground rules: "keeps working, unmodified in behavior, until
a Python screen has reached parity with the Bash menu it replaces").

**What this PR actually adds for M6**: an explicit, opt-in preview hook,
not a cutover. Setting `FORTIFY_PYTHON_TUI_PREVIEW=1` makes
`start_wizard.sh` exec `./bin/fortifylab tui --interactive` instead of
entering `main_menu` -- after the same lab-use acknowledgement, env
bootstrap, and fcli activation every path already goes through. Unset (the
default for every existing user), behavior is byte-for-byte unchanged.
This is the same "compatibility launcher, real behavior stays Bash until
proven" posture ADR 0002 already commits to, made concrete rather than
skipped.

**Still not done, tracked for a real follow-up milestone**: the fifteen
unported actions above, full parity for the seven partial ones, the fcli
lifecycle (M5's own deferral), flipping the *default* entrypoint once
parity is real, and the manual test gates from
`phase-3-python-migration.md` -- those need a human with a real terminal
and a live MicroK8s cluster, neither of which exists in the sandbox this
branch was built in. None of that is faked here.

**Done when:** an operator can opt into the Python TUI without it
becoming the default, and every existing operator's `./start_wizard.sh`
behavior is provably unchanged. Both met in this PR, verified by tests
that exercise the actual hook (not just its presence) and by the
pre-existing wizard contract tests continuing to pass unmodified.

### M7 — Flight Plans screen (first pick from the post-M6 follow-up)

The first screen picked off the remaining-menu-parity list (see Issue
tracking below): a read-only Flight Plans screen (`versions_menu()`'s
preview half in `scripts/wizard/menu.sh`), wired to the `tools` menu item
(its description already says "fcli readiness, versions, registry checks,
and operator utilities" -- this covers the "versions" part).

- `src/fortifylab/tui/screens/flight_plans.py` — `FlightPlansScreen` lists
  every Flight Plan in the catalog (via the existing, unmodified
  `fortifylab.domain.flight_plans`/`fortifylab.services.flight_plan_service`
  from M1), marks the default, and on `enter` shows a plan's components
  plus a live comparison against the current `.env`
  (`FlightPlanService.compare_env`, also unmodified).
- Read-only, same rationale as `ConfigurationScreen` skipping free-text
  edits in M4: promoting a candidate, applying a plan (which writes
  `.env`), and Docker Hub discovery all stay
  Bash/`scripts/tools/flight-plans.py`-only for now -- those are real
  writes and this screen has no text-entry widget to gate them with the
  care the Bash flow already takes.

**Done when:** `FlightPlansScreen` is reachable from the main menu (`o` on
Tools); every catalog plan renders; a plan's components compare correctly
against `.env` (aligned/drifted/review-required); a missing or malformed
catalog shows an error instead of crashing. All met in this PR.

### M8 — Sample apps folded into Applications (second pick from the follow-up)

The second slice of #446: `sample_apps_menu()`'s start/stop actions
(Juice Shop, WebGoat, DVWA). Bash keeps this on a separate menu number
from `apps_menu()`, but the underlying operation shape is identical
(`OperationCatalog.app()` already treats every app the same way --
a start/stop script and an optional destroy with a confirmation phrase),
so rather than building a second near-identical screen, the three sample
apps became three more rows on the existing `ApplicationsScreen`, labeled
`(sample)`.

- `src/fortifylab/operations/catalog.py` — `OperationCatalog.app()`'s
  script-path table gained `juice-shop`, `webgoat`, `dvwa`, mapped to
  `apps/samples/<id>/{action}.sh` (a different path shape than the core
  apps' `apps/<id>/{action}.sh` -- worth its own test, since it's an easy
  template to get wrong for a new app id).
- `src/fortifylab/tui/screens/applications.py` — `_APPS` gained the three
  sample apps; no other logic changed (same dry-run/arm/run/destroy-free
  behavior as the four core apps).

**Done when:** all three sample apps appear as start/stop rows on
`ApplicationsScreen`, run through the same real `OperationCatalog`/
`OperationRunner` path as the core apps, and `OperationCatalog.app()` has
a test locking in the `apps/samples/<id>/` path shape so a future core-app
addition doesn't silently reuse the wrong template. All met in this PR.

### M9 — Kubernetes Dashboard access screen (third pick from the follow-up)

The third slice of #446: the ephemeral-token half of
`dashboard_access_menu()` in `scripts/wizard/operations.sh`. Unlike M7/M8,
no existing `OPERATOR_MENU` item fit this -- `dashboard` covers lab health
(`live_status`), `applications` covers app *lifecycle* including the
Dashboard's own deploy/destroy, but none of the ten items covered
*generating access tokens for it*. Added a new item,
`MenuItem("kubernetes-dashboard", "Kubernetes Dashboard", ...)`.

- `src/fortifylab/services/dashboard_access_service.py` (new) — namespace
  resolution (`kubernetes-dashboard` vs `kube-system`, matching Bash's own
  fallback), a resource-readiness check, and `kubectl create token` for
  the viewer/admin service accounts.
- `src/fortifylab/tui/screens/dashboard_access.py` (new) —
  `DashboardAccessScreen`: `v` generates a 1-hour view-only token with no
  confirmation (matching Bash, which doesn't confirm this option either);
  `m` generates a 1-hour administrator token, gated by the same
  `Armable` arm-then-execute pattern as `ApplicationsScreen`/
  `GuidedDeployScreen` (Bash gates this with a plain y/N confirm, which
  the arm pattern already expresses -- no typed phrase needed here, unlike
  destroy). Caught and fixed before any review: pressing `v` while armed
  (intending `m`) must disarm too, or a stale arm meant for the admin
  token could silently carry over to a later `m` press.
- **Scope trim, deliberate**: persistent (non-expiring) tokens are not
  wired. Bash requires typing the literal word `PERSISTENT` to create a
  persistent administrator token -- the same typed-confirmation blocker as
  destroy, and there's still no text-entry widget to gate it with the same
  care. Bash's auto-repair-by-redeploying-the-Dashboard fallback also
  isn't ported: that's a deploy operation, out of scope for an
  access-token screen. This service only reports whether Dashboard
  resources exist; it never silently redeploys anything.

**Done when:** `DashboardAccessScreen` is reachable from the main menu
(`o` on Kubernetes Dashboard); a view-only token generates without
confirmation; an admin token requires arming first and auto-disarms after
one generation, matching every other armed screen's one-shot posture;
missing Dashboard resources show an error instead of crashing or
silently redeploying. All met in this PR.

## What this PR actually delivers

M1 through M6, plus M7 (Flight Plans screen), M8 (sample apps), and M9
(Kubernetes Dashboard access) as the first three picks from the post-M6
follow-up -- M6 delivered as an opt-in preview hook, not a default
cutover, because the parity that cutover depends on doesn't exist yet.
Full menu parity (M7 is one of ~15 remaining actions), the fcli lifecycle,
and the actual default flip are real, sizeable follow-on work, tracked
here rather than claimed. This keeps the claim in this document honest:
an 11,000-line Bash wizard does not get ported in one PR, and pretending
otherwise would just move the risk from "still Bash" to "untested
Python," or worse, "silently regressed Bash."

## Issue tracking

M1-M6 were tracked under parent issue #437 (with children #438-443), all
closed as completed. Follow-up work (including M7 above) is tracked under
a new parent issue on `treisland/fortifylab`, labeled `python-tui-migration`:

- [#445](https://github.com/treisland/fortifylab/issues/445) — parent: post-M6 follow-up
- [#446](https://github.com/treisland/fortifylab/issues/446) — Remaining menu parity (~15 unported actions + narrower-than-Bash gaps; M7 above is the Flight Plans slice of this)
- [#447](https://github.com/treisland/fortifylab/issues/447) — fcli activation/trust-import lifecycle (blocked on Bash-side churn slowing down)
- [#448](https://github.com/treisland/fortifylab/issues/448) — Default entrypoint cutover (blocked on #446 + manual test gates)

The parent issue lists all three and is the place to check current status; this
document is the place to check *scope and acceptance criteria* for each one.
