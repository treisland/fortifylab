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

Repo owners can draft new plan candidates with the discovery helper:

```bash
./scripts/tools/discover-flight-plans.sh --family 26.2
```

The helper queries known Docker Hub repositories and writes a candidate TOML file
under `tmp/flight-plan-candidates/` by default. It does not promote the candidate
into `config/flight-plans.toml`. Promotion is a manual owner step after reviewing
the generated versions, filling any unknown component values, testing a lab
deployment, and updating docs or release notes.

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
