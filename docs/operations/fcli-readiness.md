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

Then open **Tools and FCLI readiness -> Install or update FCLI**. The wizard
downloads the pinned Linux release asset, verifies the `.sha256` checksum,
extracts `fcli` into the user-local install directory, adds that directory to the
current shell `PATH`, and persists the PATH handoff in the selected shell
profile when it is not already present.

You do not need to run this manually every session: the wizard also
re-activates fcli's `PATH` automatically on every launch whenever it detects
fcli already installed but not yet on `PATH` in the current shell — the same
transparent detect-and-fix treatment it gives microk8s/docker group access.

If Fortify Lab TLS certificates already exist, the install flow also activates
fcli lab TLS trust for the current shell and persists only non-secret truststore
location/type hints. It does not write the truststore password to shell profiles.

FCLI is warning-only for Fortify Lab deployment. Missing or mismatched FCLI does
not block Guided deployment, Express deployment, component start/upgrade, or
lifecycle operations.

## Lab TLS trust

fcli is Java-based, so browser trust and operating-system trust are not always
enough for local mkcert certificates. The wizard configures this automatically
in two places, so you normally never need to touch it directly:

- On every launch, whenever the lab truststore exists and trust isn't yet
  active for the current shell.
- Immediately after **Certs + Secrets -> Generate certs + secrets** rebuilds
  the truststore, so a certificate rotation never leaves fcli trusting stale
  certs.

Use **Tools and FCLI readiness -> Configure fcli trust for lab TLS** only to
force a re-check or recover from an unusual state.

The wizard sets these values for the current shell:

```bash
export FCLI_TRUSTSTORE="$FCLI_CLIENT_TRUSTSTORE"   # certs/fcli-truststore, not certs/truststore
export FCLI_TRUSTSTORE_TYPE="JKS"
export FCLI_TRUSTSTORE_PWD="<DEFAULT_PASS from private .env>"
```

`certs/truststore` and `certs/fcli-truststore` are deliberately different
files. `certs/truststore` is SSC's own server-side JVM truststore (mounted
into the pod) and is narrow on purpose: just the lab CA and
`update.fortify.com`'s root CA. `certs/fcli-truststore` is fcli's own client
truststore: the same two anchors layered onto a copy of the JDK's default CA
bundle, since fcli is a client that also needs to reach arbitrary external
Fortify infrastructure (for example `fcli tool ... install`), not only the
lab and rulepack updates. Pointing fcli at the narrow `certs/truststore`
instead produces PKIX certificate validation failures for anything outside
the lab and `update.fortify.com`.

Only the non-secret truststore path and type are persisted for future shells.
In addition, it calls fcli's own persistent trust command —
`fcli config truststore set --file <fcli-truststore> --type jks --password <DEFAULT_PASS>`
— so trust is active for every future shell and fcli invocation, not just the
one the wizard happens to be running in. This is the usual fix for fcli `PKIX`
certificate validation failures against the local SSC URL, and it now requires
no manual step at all in the common case.

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
and keep local SSC login separate from FoD commands. The intended Local SSC path
is trust -> token guidance -> login/discovery -> doctor/inventory -> optional
app-version and FPR actions -> policy/summary -> logout cleanup.

## FoD optional path

Fortify on Demand examples are included only as optional command shapes. Keep
FoD tenant, client ID, and client secret values outside this repository and log
out of the session when finished.

For classroom or workshop practice, use the FoD fcli training runbooks in
`runbooks/training/fcli-fod/`. They keep FoD as an explicit external-SaaS
boundary and avoid printing configured secret values.
