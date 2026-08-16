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
without printing secrets.

## Repo-owner discovery workflow

Repo owners can draft and curate new plan candidates with the discovery helper.
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
and reuses existing catalog values when a repository cannot be listed.

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

## Rollback expectations

Changing Flight Plans is configuration rollback, not data rollback. Restoring an
older `.env` backup returns version settings to previous values, but it does not
undo database schema migrations, Helm release history, Kubernetes Secrets, PVC
contents, or application-generated data.

Before moving to an older Fortify version after a deployment has run:

1. Export or snapshot any data you intend to keep.
2. Review Fortify product and chart downgrade guidance.
3. Prefer a full lab reset when the rollback crosses database or schema
   boundaries.
4. Keep database version changes deliberate and separate from Flight Plan changes.
