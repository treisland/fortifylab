# Fortify Lab on Kubernetes

A scripted Fortify deployment for evaluation, training, and demos:
**SSC**, **ScanCentral SAST**, **ScanCentral DAST**, **LIM**, plus the
Kubernetes Dashboard, all running on [microk8s](https://microk8s.io/) with
mkcert-issued TLS. Fortify Lab is now a Python CLI/TUI-first operator tool,
with retained Bash scripts only at the operation-adapter and bootstrap edges.

> Not a production deployment guide — opinionated defaults, single-node
> cluster, NFS PVCs. Intended for lab and evaluation use.

📖 **Full documentation:** [treisland.github.io/fortifylab](https://treisland.github.io/fortifylab/)
— this README is a fast on-ramp; the docs site is the complete, authoritative
reference (getting started, troubleshooting, architecture, operations).

## Contents

- [Scope](#scope)
- [What you get](#what-you-get)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Using Fortify Lab](#using-fortify-lab)
- [DNS and TLS](#dns-and-tls)
- [Manual configuration after deploy](#manual-configuration-after-deploy)
- [Repo layout](#repo-layout)
- [Conventions and gotchas](#conventions-and-gotchas)
- [Cleanup](#cleanup)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [License](#license)

## Scope

This repository intentionally has one job: guide an operator through creating
and running a Fortify lab from the terminal. The supported application
entrypoint is the Python CLI/TUI at `./bin/fortifylab`. Kubernetes Dashboard
provides cluster monitoring. The repository does not include a Fortify Lab web
UI, an autonomous SDLC supervisor, Telegram/GitHub automation, or an ASPM.
Those are separate products with different users and security boundaries.

## What you get

| Component | Default URL | Notes |
|---|---|---|
| Software Security Center (SSC) | `https://ssc.fortifydemo.com` | Central app, MySQL 8 backed |
| ScanCentral SAST | `https://sast.fortifydemo.com` | Controller + Linux workers |
| ScanCentral DAST | `https://dast.fortifydemo.com` | API + scanner, PostgreSQL 17 backed |
| LIM | `https://lim.fortifydemo.com` | DAST license/pool server |
| Kubernetes Dashboard | `https://dashboard.fortifydemo.com` | Deployed by default; short-lived access tokens |

Also included: optional **vulnerable sample applications** (Juice Shop,
WebGoat, DVWA) for a first scan with no source of your own, and a **Flight
Plans** system that bundles known-compatible component versions so you pick
one plan instead of tuning versions by hand — see [Versions and
compatibility](docs/operations/versions-and-compatibility.md).

## Prerequisites

- Linux host (Ubuntu 22.04+ tested; other distros are untested)
- Python 3.11+ available as `python3` (Ubuntu 22.04 ships 3.10 by default; install
  a newer interpreter, e.g. `sudo apt install python3.12`, if `python3 --version`
  reports below 3.11) — required by the Flight Plans version-selection tool
- ~16 GB RAM, ~50 GB disk free
- Browser reachability to the host (LAN IP, public IP, or VPN)
- A Fortify license (`fortify.license`), stored outside the repository when
  desired — see [`secrets/input/README.md`](secrets/input/README.md)
- A Docker Hub login that can pull from `fortifydocker/*` and `bitnamilegacy/*`
- For DAST: ScanCentral DAST and WebInspect licenses loaded into LIM before
  DAST scans can run successfully

MicroK8s itself does not need to be pre-installed. Fortify Lab's guided setup
installs it and other host prerequisites; see
[`scripts/install_microk8s.sh`](scripts/install_microk8s.sh) if you'd rather
run that step by hand first.

## Quick start

```bash
git clone https://github.com/treisland/fortifylab.git
cd fortifylab
cp .env.example .env
# Edit .env: at minimum set DOMAIN, DEFAULT_PASS, FORTIFY_LICENSE_FILE,
# and check image versions. The repository-local license default still works.
./bin/fortifylab --help
./bin/fortifylab doctor --check
./bin/fortifylab status --check
./bin/fortifylab tui --check
```

`./bin/fortifylab` is the supported application surface for operator checks,
configuration diagnostics, offline help, runbook contracts, and the emerging
TUI. The first guided deployment experience continues to carry the **LAB /
DEMO USE ONLY** boundary described in [`docs/lab-use.md`](docs/lab-use.md);
that limitation applies to this deployment toolkit, not to the production
capabilities of Fortify products.

**What to expect:** allow roughly 15–20 minutes for Express deployment once
prerequisites and images are already available, and 30–60 minutes for a
first run on a fresh host (package installs and image pulls dominate). Guided
mode shows a live status board and an estimate for the current step, so it
won't look stuck. Full walkthrough, including expected screen-by-screen
output: [Getting started](docs/getting-started/index.md).

If a step fails, fix the reported dependency and retry the same step, or quit
safely and come back later. Resume/repair picks up at the first incomplete
step and never deletes data on its own.

### Supported entrypoints

The Python CLI/TUI is the supported architecture:

```bash
./bin/fortifylab --help
./bin/fortifylab doctor --check
./bin/fortifylab status --check
./bin/fortifylab help topic ssc --check
./bin/fortifylab config diagnostics
./bin/fortifylab tui --check
```

`./start_wizard.sh` remains only as a compatibility shim through M8 for these
legacy aliases:

```bash
./start_wizard.sh --help
./start_wizard.sh doctor          # delegates to ./bin/fortifylab doctor --check
./start_wizard.sh status          # delegates to ./bin/fortifylab status --check
./start_wizard.sh help topic ssc  # delegates to ./bin/fortifylab help topic ssc --check
./start_wizard.sh config-diagnostics
```

Do not add new interactive application behavior to `start_wizard.sh` or
`scripts/wizard/`; the retired Bash wizard internals have been removed. Retained
Bash scripts are low-level adapters for host setup, certificates, secrets, and
component lifecycle actions that the Python operation catalog can preview and
call deliberately.

Install `requirements-python.txt` only if you're developing the CLI/TUI slices
(kept separate from `requirements-docs.txt`, which is
for building the documentation site):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-python.txt
```

## Using Fortify Lab

The CLI/TUI direction is task-oriented: Deploy / Resume, Applications,
Configuration, Runbooks, Logs, Diagnostics, Certificates & Trust, Tools, and
Help. Current clone-safe commands include:

- `./bin/fortifylab doctor --check` for read-only health checks.
- `./bin/fortifylab status --check` for a non-mutating status summary.
- `./bin/fortifylab config diagnostics` for `.env` host and URL wiring.
- `./bin/fortifylab help topic <id> --check` for offline help topics.
- `./bin/fortifylab tui --check` for the deterministic TUI smoke contract.

Guided deployment, express deployment, resume/repair, and lifecycle controls
are being carried into Python while preserving the existing operation behavior.
The retained Bash scripts under `scripts/` and `apps/**/{start,stop,destroy}.sh`
remain implementation adapters, not the supported interactive application flow.

Full menu tour, screen-by-screen: [Getting started](docs/getting-started/index.md).
Stuck on something specific: [Troubleshooting](docs/troubleshooting/index.md).

## DNS and TLS

The lab issues TLS certs for the wildcard `*.$DOMAIN` (default
`fortifydemo.com`) and needs that domain to resolve both on your browser and
inside the cluster. The wizard's **Advanced setup and configuration →
Configure DNS** step handles the in-cluster half; you handle the client half
(add the lab node's IP to `/etc/hosts` for each hostname, or your resolver).
To make your browser trust the lab CA:

```bash
# From your laptop:
scp ubuntu@<host>:~/fortifylab/certs/rootCA.pem ~/Downloads/fortify-rootCA.pem
# macOS: Keychain Access → System keychain → drag in rootCA.pem → double-click → Always Trust
# Linux:  sudo cp ~/Downloads/fortify-rootCA.pem /usr/local/share/ca-certificates/fortify-rootCA.crt && sudo update-ca-certificates
# Firefox: about:preferences#privacy → Certificates → import as authority
```

Re-running `create-certs.sh` rotates the root CA — you'll need to re-import.
Full details, including the Traefik `TRAEFIK DEFAULT CERT` recovery steps:
[Networking, URLs, and TLS](docs/operations/networking-and-tls.md).

## Manual configuration after deploy

Two steps still need a human after `Deploy from scratch`:

- **SSC access and ControllerToken** — log into SSC as `admin`, create a
  `ScanCentralCtrlToken` under Administration → ScanCentral SAST → Tokens,
  then run wizard **Configure → Apply SSC ControllerToken** (hidden input;
  the wizard patches the Secret directly, never writes the token to a file).
- **DAST license + pool in LIM** — sign into LIM as `lim_admin`, upload the
  DAST license, create a pool named `Default` (matches `LIM_POOL_NAME`), then
  redeploy ScanCentral DAST so the scanner can authenticate.

Full walkthrough, including Kubernetes Dashboard token options and the first
scan handoff: [Getting started](docs/getting-started/index.md).

## Repo layout

```
.env.example              Template — copy to .env, edit DOMAIN/passwords/versions.
bin/fortifylab            Primary Python CLI/TUI entrypoint.
fortifylab/               Supported Python application package.
start_wizard.sh           M7/M8 compatibility shim for supported legacy aliases.
setup.sh                  Convenience launcher that currently delegates through the shim.
scripts/
  create-certs.sh         mkcert root + leaf, JKS keystore, JVM truststore.
  create-secrets.sh       k8s Secrets: explicit per-key, no folder dump.
  install_microk8s.sh     microk8s + addons.
  tools/flight-plans.py   Component-version bundle catalog (list/show/promote-local/...).
secrets/
  input/                  User-provided files (license). Gitignored.
  templates/              Committed templates rendered at deploy time.
  generated/              Build artifacts. Wiped + rebuilt every run.
  README.md               Full file → Secret → consumer map.
apps/
  mysql, postgresql       Bitnami legacy charts.
  ssc, lim                Fortify charts.
  scsast                  ScanCentral SAST controller + workers.
  scdast/core, scdast/scanner   ScanCentral DAST.
  kubernetes-dashboard    Default operational Web UI and bounded token RBAC.
docs/                     Full documentation site (MkDocs) — authoritative source.
tests/                    Python test suite (unittest); run before opening a PR.
```

## Conventions and gotchas

- **Run as your normal user**, never `sudo ./bin/fortifylab`. mkcert is
  per-user; running as root would create a different CA at `/root/...` and
  silently rotate every cert. `create-certs.sh` and `create-secrets.sh`
  refuse to start under sudo.
- **Image tags are pinned in `.env.example`** to specific versions of
  `bitnamilegacy/postgresql`, `bitnamilegacy/mysql`, etc. Bitnami's
  `:latest` tag has shifted under us before — always pin.
- **SSC `secret.key` is preserved across `create-secrets.sh` runs** because
  SSC uses it to encrypt credentials in its database. A fresh clone starts
  with the committed lab sample. Do not replace that key after SSC stores
  data; recovery and deliberate migration guidance is in
  [`secrets/README.md`](secrets/README.md).
- **`FORTIFY_LICENSE_FILE`** may reference a protected license outside the
  repository. The default remains `secrets/input/fortify.license`.
  `secrets/generated/` is owned by the scripts. License paths and content must
  never be included in logs, artifacts, or support bundles.
- **Re-running `create-certs.sh`** rotates the root CA. Browsers will
  flag the new cert as untrusted until you re-import `rootCA.pem`. Rerun the
  Secrets step afterward so Kubernetes `fortify/tls` and the MicroK8s ingress
  default certificate use the regenerated mkcert leaf.
- **Postgres data directory is initialized by the running image**. If
  the chart's image ever ships a newer major (PostgreSQL 18 vs 17), the
  PVC must be wiped to re-init. We pin the image tag to avoid surprise
  upgrades.
- **Re-running the wizard is safe.** Resume/repair and Start/Upgrade never
  delete persistent data on their own; only the explicit, confirm-gated
  **Destroy** action under a component's expert menu does.

## Cleanup

```bash
./bin/fortifylab --help
# Use the Python CLI/TUI lifecycle surface or the retained low-level adapter
# scripts intentionally for each component.
# Then on the host:
microk8s helm -n fortify list                     # confirm none remain
microk8s kubectl delete namespace fortify         # nuke everything else
```

## Contributing

PRs welcome. Before opening one:

```bash
python3 -m unittest discover -s tests    # run the test suite
./scripts/validate-docs.sh               # if you touched docs/
```

See [Contributing documentation](docs/contributing/index.md) for the full
docs-as-code workflow (sources of truth, screenshot sanitization, wizard help
mappings, review checklist).

For deployment errors, start with the read-only Python checks
`./bin/fortifylab doctor --check` and `./bin/fortifylab status --check`. When
evidence must be shared, create a sanitized diagnostics bundle, inspect the
allow-listed archive locally, and include only that minimum evidence plus the
failed step. Do not attach raw logs,
`.env`, Secret values, license data, tokens, or private keys.

Questions or ideas: open a [GitHub issue](https://github.com/treisland/fortifylab/issues).

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for notable changes by release.

## License

MIT. See [`LICENSE`](LICENSE).
