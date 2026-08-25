# Versions and compatibility

Fortify product releases, Helm chart versions, and container image tags are
separate identifiers. `.env.example` records this repository's tested lab
profile; an override is drift, even when a pod starts successfully.

Before changing a version, compare Fortify release notes and chart requirements,
database major versions, Kubernetes compatibility, and upgrade sequencing.
Record the old profile and migration/rollback limitations. Never assume Helm
rollback reverses a schema migration, and never wipe a PVC to resolve a version
mismatch without explicit data-destruction approval.

“Tested profile” means tested for this lab topology only. It is not a production
support or compatibility certification.


## Fortify CLI

`FORTIFY_RECOMMENDED_FCLI_VERSION` pins the Fortify CLI version used by the
wizard's **Tools and FCLI readiness** screen. The default follows the current
Fortify Lab product-version profile, but FCLI remains a client-side tool: it is
not installed into Kubernetes and is not required for infrastructure deployment
profiles that only create or operate lab services.

A missing or different `fcli` version is reported as a readiness warning. Update
the pin when changing Fortify product versions, then use the Tools screen to
install or update the user-local binary and re-check `fcli --version`. Review
Fortify's fcli release notes before crossing major versions because command
options and session behavior can change.


## Fortify Flight Plans

A Fortify Flight Plan is a curated bundle of Fortify product, chart, and image
versions. The catalog lives in `config/flight-plans.toml`; the selected plan is
stored in `.env` as `FORTIFY_FLIGHT_PLAN`. Guided Setup and the Deployment
Versions menu can apply a plan with a normal `.env` backup before writing any
changes.

Flight Plans intentionally manage Fortify application components only: SSC,
ScanCentral SAST, ScanCentral DAST, and LIM. MySQL and PostgreSQL versions remain
separate controls because database upgrades, schema migrations, and data rollback
need different decisions than an application version selection.

Use the recommended Flight Plan for normal labs. Use individual overrides only
when testing a specific compatibility issue or preparing a new catalog entry.
Diagnostics compare the current `.env` against the selected plan and report drift
without printing secrets. Intentional component overrides are tracked with
`FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS` so operators can tell the difference
between a normal curated bundle and an advanced compatibility exception.

### Guided Flight Plan upgrade workflow

Use the guided Flight Plan path when the goal is to move the whole Fortify lab to
a curated release bundle.

1. Open Guided Setup or **Operational guidance -> Deployment versions and Flight
   Plan** before starting or upgrading components.
2. Select the target Flight Plan and review the upgrade plan preview. The wizard
   shows the current-vs-target comparison for each Fortify component before it
   stages changes.
3. Confirm that MySQL and PostgreSQL database versions remain separate from the
   Flight Plan. Change database versions only as an explicit database operation
   with separate migration and rollback notes.
4. Let the wizard create the normal `.env` backup and stage the selected Flight
   Plan values. Do not hand-edit `.env` during the same upgrade window unless
   you are intentionally testing drift.
5. Start or upgrade components in dependency order from the guided workflow.
   Watch the live wait screen, readiness probes, and known-issue hints before
   moving to the next component.
6. Export a sanitized diagnostics bundle after the upgrade if you need an audit
   trail or support evidence. Review the archive locally before sharing it.

### Advanced component override workflow

Use individual component overrides only for a deliberate exception: reproducing a
compatibility issue, validating a vendor hotfix, or preparing a new Flight Plan
candidate.

1. Record the selected Flight Plan baseline and the exact component key you are
   overriding, such as `FORTIFY_SSC_IMAGE_TAG` or
   `FORTIFY_SCDAST_CHART_VERSION`.
2. Compare `.env` to the selected Flight Plan before changing values so the
   starting drift is visible.
3. Change only the component under test. The resulting individual component override is drift from the curated bundle even if the app starts.
4. Run configuration diagnostics and the Flight Plan comparison again. Keep the
   diagnostic output or sanitized bundle as the audit trail for why the override
   exists.
5. Restore to the Flight Plan baseline as soon as the exception is no longer
   needed by reselecting the Flight Plan or reapplying its environment updates.
   Confirm the comparison no longer reports that component as drift.

## Post-upgrade verification

After a Flight Plan upgrade or advanced override, verify more than pod readiness:

- Run the wizard's configuration diagnostics and confirm the selected Flight
  Plan, current-vs-target comparison, database-separate entries, and release
  overlay status are visible.
- Check each upgraded Fortify component through its application URL or expected
  API path, not only Kubernetes readiness.
- Review release overlay output and known-issue guidance. Missing overlays are
  normal; selected overlays must be readable, syntax-valid, and release-specific.
- For DAST upgrades, stay aware of the documented known issue: DAST upgrade job artifact permission issue. Confirm the configured resource override is still in place when that release path needs it.
- Keep the `.env` backup path, diagnostics bundle path, and wizard log excerpt
  together as the upgrade audit trail.

## Release-aware deployment overlays

Most release changes should be handled through Flight Plan values. When a
specific Fortify release needs a deployment-script tweak, keep that tweak beside
the affected app instead of branching the entire `apps/` tree.

Overlay path convention:

```text
apps/<app-id>/releases/<major.minor>/overrides.sh
```

Examples:

```text
apps/ssc/releases/26.2/overrides.sh
apps/scdast/core/releases/26.2/overrides.sh
apps/scdast/scanner/releases/26.2/overrides.sh
```

The selected Flight Plan determines the `<major.minor>` baseline. During an app
start or upgrade, the app script sources the matching overlay when it exists.
Missing overlays are normal and mean the shared deployment script is valid for
that release. Selected overlays must pass `bash -n`; guided pre-flight and
configuration diagnostics report syntax or readability problems before the app
script runs.

Overlays should stay small and release-specific. Prefer appending Helm arguments
to `RELEASE_OVERLAY_HELM_ARGS` rather than replacing whole commands:

```bash
RELEASE_OVERLAY_HELM_ARGS+=(--set-string example.releaseSetting=true)
```

Do not place secrets, generated credentials, or environment-specific values in a
release overlay. Those belong in `.env`, Kubernetes Secrets, or the existing
configuration editor flow.

## Repo-owner discovery workflow

Repo owners curate the shared, tracked catalog (`config/flight-plans.toml`)
with the discovery helper below. Discovery itself (`discover-releases`,
`discover`) is not repo-owner-only -- any user can run it too, then add the
result to their own local Flight Plans instead (see
[Your own local Flight Plans](#your-own-local-flight-plans)). This section
covers curating the plan everyone else sees by default.

Fortify commonly publishes tags with a release prefix such as `25.2` or
`26.2`, so the helper can scan known repositories and score candidate releases:

```bash
./scripts/tools/flight-plans.py discover-releases --years 25,26
./scripts/tools/flight-plans.py curate --years 25,26
```

To write complete candidate drafts for review:

```bash
./scripts/tools/flight-plans.py discover-releases --years 25,26 --write-complete
```

To inspect or regenerate one release explicitly:

```bash
./scripts/tools/discover-flight-plans.sh --release 26.2
```

Discovery prints the selected component candidates to the terminal and writes a
TOML draft under `tmp/flight-plan-candidates/` by default. It prefers Docker Hub
tag listings, falls back to the authenticated Docker Registry API when needed,
and reuses existing catalog values when a repository cannot be listed. Discovery
only counts tags that match the requested release prefix; it does not substitute
newer tags from a different release to make coverage look complete.

`FORTIFY_SCDAST_CHART_VERSION` is shared by ScanCentral DAST Core and Scanner in
this lab, so discovery requires the release tag to exist in both
`fortifydocker/helm-scancentral-dast-core` and
`fortifydocker/helm-scancentral-dast-scanner` before counting DAST as covered.

Promotion remains an owner-controlled step. Use a dry run first, then write the
catalog only after reviewing the candidate and testing the deployment path:

```bash
./scripts/tools/flight-plans.py promote tmp/flight-plan-candidates/fortify-26.2.toml --status candidate
./scripts/tools/flight-plans.py promote tmp/flight-plan-candidates/fortify-26.2.toml --status recommended --yes
./scripts/tools/flight-plans.py validate
```

Promoting a plan as `recommended` also makes it the catalog default and demotes
the previous recommended plan to `known-good`. ScanCentral DAST Core and Scanner
container images are currently chart-managed in this lab; add explicit `.env`
keys before curating them as separate Flight Plan fields.

## Your own local Flight Plans

Discovery and drafting are not repo-owner-only: any user can add a Flight Plan
to their own local, gitignored catalog (`config/flight-plans.local.toml`)
without opening a PR or touching the shared `config/flight-plans.toml`. This is
useful for trying a release the repo owner has not reviewed yet -- for example,
a new Fortify release the day it drops.

From the wizard: **Deployment Versions and Flight Plan -> Refresh/discover
candidate Flight Plan tags**, then **Add a discovered candidate to my local
Flight Plans**. From the CLI:

```bash
./scripts/tools/flight-plans.py discover --release 26.3
./scripts/tools/flight-plans.py promote-local tmp/flight-plan-candidates/fortify-26.3.toml --status candidate
./scripts/tools/flight-plans.py promote-local tmp/flight-plan-candidates/fortify-26.3.toml --status known-good --yes
```

Local Flight Plans show up merged alongside curated ones everywhere a Flight
Plan can be selected (`list`, `show`, `env-updates`, `compare-env`, and every
wizard picker) -- they are never a separate mode you have to opt into. They
cannot be set `--status recommended`, since "the recommended plan" is a
curated-catalog-only concept. `config/flight-plans.toml` itself is never
modified by this workflow; `validate` against the curated catalog is
unaffected.

To preview a Flight Plan's component versions before selecting or upgrading to
it -- curated or your own local ones -- use **Deployment Versions and Flight
Plan -> Preview a Flight Plan's versions**, or from the CLI:

```bash
./scripts/tools/flight-plans.py show fortify-26.2
```

To remove one of your own local Flight Plans, use **Deployment Versions and
Flight Plan -> Remove a local Flight Plan**, or from the CLI:

```bash
./scripts/tools/flight-plans.py list --local-only
./scripts/tools/flight-plans.py remove-local fortify-26.3 --yes
```

Only plans in your local catalog can be removed this way; the shared curated
catalog is never touched. To change a local plan's component versions instead
of removing it, re-run `discover` and `promote-local` for the same id --
`promote-local` upserts by plan id, so this overwrites the existing local
entry in place.

## Applying a Flight Plan

Everything above manages *which Flight Plans exist*. The old Bash wizard
`apply-flight-plan` command is not part of the supported M7 compatibility shim.
Until a Python command restores this write path, apply a plan by reviewing it
with `./scripts/tools/flight-plans.py show <plan-id>`, updating `.env`
deliberately, and keeping a backup of the previous file.

## Rollback expectations

Changing Flight Plans is configuration rollback, not data rollback. Restoring an
older `.env` backup returns version settings to previous values, but it does not
undo database schema migrations, Helm release history, Kubernetes Secrets, PVC
contents, or application-generated data.

Treat snapshots as a data-safety boundary, not as permission to experiment
without a rollback plan. A filesystem, VM, or PVC snapshot can preserve bytes
while still capturing an in-flight database or incompatible schema state. Record
what was snapshot, when it was taken, and which database/application versions it
belongs to before applying the upgrade plan.

Before moving to an older Fortify version after a deployment has run:

1. Export or snapshot any data you intend to keep.
2. Review Fortify product and chart downgrade guidance.
3. Prefer a full lab reset when the rollback crosses database or schema
   boundaries.
4. Keep database version changes deliberate and separate from Flight Plan changes.
