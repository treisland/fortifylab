# Tools and FCLI readiness

The wizard's **Tools and FCLI readiness** screen prepares the local operator
shell for Fortify command-line work after the lab is deployed. It is a readiness
handoff, not a scan-submission workflow.

## Install or update

Set the recommended version in `.env` when you need to override the tested
profile:

```bash
export FORTIFY_RECOMMENDED_FCLI_VERSION="3.23.3"
export FORTIFY_FCLI_INSTALL_DIR="$HOME/fortify/tools/bin"
```

Then open **Tools and FCLI readiness → Install or update FCLI**. The wizard
downloads the pinned Linux release asset, verifies the `.sha256` checksum, and
extracts `fcli` into the user-local install directory. Add that directory to
`PATH` if your shell does not already find it:

```bash
export PATH="$HOME/fortify/tools/bin:$PATH"
fcli --version
```

FCLI is warning-only for Fortify Lab deployment. Missing or mismatched FCLI does
not block Guided deployment, Express deployment, component start/upgrade, or
lifecycle operations.

## SSC-primary handoff

Use SSC as the primary lab system of record. The wizard prints templates using
`SSC_URL` and `SCSAST_CTRL_URL`, then leaves every secret as a placeholder. Paste
real token values only into a private shell or interactive `fcli` prompt. Do not
write filled commands into `.env`, generated scripts, wizard logs, screenshots,
or diagnostics.

The readiness templates cover session creation, destination inspection, and the
shape of a later `sc-sast scan start` command against a prebuilt package or MBS
file. They intentionally do not create sample applications, package source, or submit a first scan. Use the [first-scan walkthrough](first-scan.md) when you are
ready for that separate lifecycle.

For repeatable operator checks, use the official Fortify Lab fcli runbooks in
`runbooks/official/fcli/` or read the [fcli runbook notes](../runbooks/fcli.md).
Those runbooks follow the official [fcli v3 documentation](https://fortify.github.io/fcli/v3/)
and keep local SSC login separate from FoD commands.

## FoD optional path

Fortify on Demand examples are included only as optional command shapes. Keep
FoD tenant, client ID, and client secret values outside this repository and log
out of the session when finished.

For classroom or workshop practice, use the FoD fcli training runbooks in
`runbooks/training/fcli-fod/`. They keep FoD as an explicit external-SaaS
boundary and avoid printing configured secret values.
