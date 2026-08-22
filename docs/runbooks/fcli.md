# FCLI Runbooks

Fortify Lab-maintained fcli runbooks live in `runbooks/official/fcli/`. They are
small operator helpers for local lab validation, not product replacements or
FoD automation.

Use the official [fcli v3 documentation](https://fortify.github.io/fcli/v3/) as
the command reference. These runbooks only wrap the SSC-first lab defaults that
Fortify Lab already exposes through `.env` and the wizard.

## Runbooks

- `inspect-fcli-foundation.sh` reports the resolved fcli binary, installed
  version, recommended lab version, configured fcli data directories, and SSC
  session list when available.
- `configure-lab-trust.sh` checks the generated lab JKS truststore and shows the
  secret-safe fcli TLS trust handoff used to avoid local SSC `PKIX` failures.
- `ssc-token-guidance.sh` shows how to prepare and clean up an SSC token
  environment variable without printing or storing the token value.
- `local-ssc-login-discovery.sh` logs in to the local SSC lab using a token read
  from an environment variable, then lists a bounded set of SSC application
  versions for discovery.
- `local-ssc-create-appversion.sh` creates or reuses a local SSC application
  version after `CONFIRM_LOCAL_SSC_CREATE=yes`.
- `local-ssc-upload-fpr.sh` validates a readable local `.fpr` file path and
  uploads it to the application version after `CONFIRM_LOCAL_SSC_UPLOAD=yes`.
- `local-ssc-policy-check.sh` runs the fcli SSC `check-policy` action for the
  selected application version and returns the action exit code.
- `local-ssc-appversion-summary.sh` writes the fcli SSC `appversion-summary`
  issue summary to `stdout` or a selected output file.
- `local-ssc-session-doctor.sh` checks the resolved fcli runtime, session-list
  support, optional token variable presence, and a bounded authenticated SSC
  application-version query for the default `fortifylab` session.
- `local-ssc-inventory.sh` lists bounded SSC application and application-version
  inventory through an existing local SSC session.
- `local-ssc-logout-cleanup.sh` logs out the named SSC session, then prints the
  remaining session summary without reading fcli session files.

## Local SSC Scope

The local SSC flow uses `SSC_URL` and, when present, `SCSAST_CTRL_URL`.
Authentication is SSC-only through `fcli ssc session login`. If the session will
also be used for ScanCentral SAST commands, export
`FCLI_DEFAULT_SSC_CLIENT_AUTH_TOKEN` in a private shell before login.

Token values must not be pasted into runbook parameters, committed files,
screenshots, wizard logs, generated diagnostics, or shared terminals. The login
runbook accepts only the name of the environment variable that contains the SSC
token, then passes it to fcli through `FCLI_DEFAULT_SSC_TOKEN` for the login
process rather than placing the token on the command line. If the variable is
missing, it prints a redacted command shape and exits without attempting login.

The wizard configures fcli trust automatically on every launch and right after
certs are regenerated, so a `PKIX` or certificate validation error here usually
means the wizard hasn't been (re)launched since certs last changed. Run **Tools
and FCLI readiness -> Configure fcli trust for lab TLS** or the
`configure-lab-trust.sh` runbook to force a re-check before retrying login.

FoD is separate from this local SSC runbook set. Use `fcli fod ...` only for a
deliberate FoD workflow with FoD tenant/client credentials kept outside this
repository.

## Environment Defaults

Common local defaults:

```bash
export SSC_URL="https://ssc.example.test"
export SCSAST_CTRL_URL="https://sast.example.test"
export FORTIFY_RECOMMENDED_FCLI_VERSION="3.23.3"
export FORTIFY_FCLI_INSTALL_DIR="$HOME/fortify/tools/bin"
export FCLI_BIN="$FORTIFY_FCLI_INSTALL_DIR/fcli"
export FCLI_DEFAULT_SSC_TOKEN="<set privately>"
export FCLI_TRUSTSTORE="$FORTIFY_CERTS/fcli-truststore"  # not certs/truststore -- see fcli-readiness.md
export FCLI_TRUSTSTORE_TYPE="JKS"
export FCLI_TRUSTSTORE_PWD="<DEFAULT_PASS from private .env>"
```

For fcli v3 state isolation, use the official fcli data-directory environment
variables when needed:

```bash
export FCLI_DATA_DIR="$HOME/.fortify/fcli-lab"
export FCLI_STATE_DIR="$FCLI_DATA_DIR/state"
export FCLI_CONFIG_DIR="$FCLI_DATA_DIR/config"
```

Log out of SSC sessions when finished:

```bash
fcli ssc session logout --ssc-session fortifylab
```

The logout cleanup runbook uses the same default session name and can also print
configured fcli state directory paths for orientation. It never prints token
values, session file contents, or fcli state file contents.

## Recommended Local SSC Flow

Use this order for a clean operator workflow: trust -> token guidance -> login,
then use session doctor or inventory to confirm access, optionally create an
application version and upload an FPR, run policy/summary checks, then log out
and unset the token.

## Local SSC FPR Flow

After logging in with `local-ssc-login-discovery.sh`, a bounded demo sequence is:

```bash
APPVERSION="Fortify Lab Training:Synthetic" \
CONFIRM_LOCAL_SSC_CREATE=yes \
runbooks/official/fcli/local-ssc-create-appversion.sh

APPVERSION="Fortify Lab Training:Synthetic" \
FPR_FILE="./results/synthetic.fpr" \
CONFIRM_LOCAL_SSC_UPLOAD=yes \
runbooks/official/fcli/local-ssc-upload-fpr.sh

APPVERSION="Fortify Lab Training:Synthetic" \
runbooks/official/fcli/local-ssc-policy-check.sh

APPVERSION="Fortify Lab Training:Synthetic" \
runbooks/official/fcli/local-ssc-appversion-summary.sh
```

The create and upload runbooks are mutating and default to no-op previews until
their confirmation parameters are set to `yes`. The upload runbook checks that
`FPR_FILE` is a readable local `.fpr` file before it can call fcli.
