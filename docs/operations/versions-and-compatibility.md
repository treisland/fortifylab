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
