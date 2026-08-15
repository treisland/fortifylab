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
- `local-ssc-login-discovery.sh` logs in to the local SSC lab using a token read
  from an environment variable, then lists a bounded set of SSC application
  versions for discovery.

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
