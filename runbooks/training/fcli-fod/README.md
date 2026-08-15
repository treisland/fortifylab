# FoD fcli Training Runbooks

These Bash runbooks adapt the useful FoD workshop sequence from
`SE-AppSecSandbox/fcli_workshop` into Fortify Lab's runbook library:
environment/session check, release and entitlement guidance, package/upload,
wait/status, policy check, and release summary.

Fortify on Demand is external SaaS. Keep tenant URLs, API client IDs, secrets,
tokens, passwords, and customer release names out of shared logs, screenshots,
diagnostic bundles, and committed files.

The runbooks detect both workshop-style `FCLI_DEFAULT_*` values and fcli action
`FOD_*` values, but they print only whether each variable is set. Secret values
are never echoed by these scripts.

Suggested classroom order:

1. `00-fod-env-session-check.sh`
2. `10-release-entitlement-guidance.sh`
3. `20-package-and-upload.sh`
4. `30-wait-and-status.sh`
5. `40-policy-check.sh`
6. `50-release-summary.sh`

The upload runbook requires `CONFIRM_EXTERNAL_FOD_UPLOAD=yes` before it submits
to FoD. Use `LOGIN_IF_NEEDED=true` only in a private shell when you want fcli to
login using already configured defaults.
