# Fortify Lab on Kubernetes

A scripted Fortify deployment for evaluation, training, and demos:
**SSC**, **ScanCentral SAST**, **ScanCentral DAST**, **LIM**, plus the
Kubernetes Dashboard, all running on [microk8s](https://microk8s.io/) with
mkcert-issued TLS. Every step driven by an interactive wizard or a single
"deploy from scratch" command.

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
- [Using the wizard](#using-the-wizard)
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
and running a Fortify lab with the interactive wizard. Kubernetes Dashboard
provides cluster monitoring. The repository does not include a second Web UI,
an autonomous SDLC supervisor, Telegram/GitHub automation, or an ASPM. Those
are separate products with different users and security boundaries.

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

MicroK8s itself does not need to be pre-installed — the wizard's guided setup
installs it (and other host prerequisites) for you; see
[`scripts/install_microk8s.sh`](scripts/install_microk8s.sh) if you'd rather
run that step by hand first.

## Quick start

```bash
git clone https://github.com/treisland/fortifylab.git
cd fortifylab
cp .env.example .env
# Edit .env: at minimum set DOMAIN, DEFAULT_PASS, FORTIFY_LICENSE_FILE,
# and check image versions. The repository-local license default still works.
./start_wizard.sh
```

The first launch shows a Fortify Lab banner and a mandatory **LAB / DEMO USE
ONLY** notice — type `LAB` to acknowledge it. That limitation applies to this
deployment toolkit, not to the production capabilities of Fortify products;
see [`docs/lab-use.md`](docs/lab-use.md). From there, the welcome screen
recommends **Guided deployment** for first-time use: a numbered,
explanatory walkthrough that installs host prerequisites, then TLS, secrets,
databases, and each Fortify component in dependency order.

**What to expect:** allow roughly 15–20 minutes for Express deployment once
prerequisites and images are already available, and 30–60 minutes for a
first run on a fresh host (package installs and image pulls dominate). Guided
mode shows a live status board and an estimate for the current step, so it
won't look stuck. Full walkthrough, including expected screen-by-screen
output: [Getting started](docs/getting-started/index.md).

If a step fails, fix the reported dependency and retry the same step, or quit
safely and come back later — choose **Resume or repair** and the wizard picks
up at the first incomplete step. It never deletes data on its own.

### Python CLI preview

A Python CLI/TUI migration is in progress alongside the Bash wizard. Bash remains the production guided wizard and compatibility entrypoint; the
preview commands run from a clone with the standard library only:

```bash
./bin/fortifylab --help
```

A real interactive main menu (arrow keys or `j`/`k`, number keys, `enter` to
preview, `q` to quit) is available from a terminal with:

```bash
./bin/fortifylab tui --interactive
```

Every item on the main menu now opens a real screen (press `o` to open) —
none is preview-only anymore, though some still cover only part of their
Bash counterpart's actions (noted below): **Dashboard** (a lab-wide
readiness board — 11 ready/warn checks ported from Bash's own setup
readiness board, plus a recommended next action), **Deploy / Resume** (a
Guided deployment screen for the SSC-only profile), **Applications**
(live per-app status -- "N/N running"/"N/M ready"/"not deployed",
color-coded like Bash's own `app_status()` -- then Start/Upgrade, Stop,
Logs, and Show URL & credentials for ssc/lim/mysql/postgresql and the
sample apps Juice Shop/WebGoat/DVWA), **Lab Lifecycle** (bulk
shutdown/start scoped to the active deployment profile or the whole lab),
**Configuration** (redacted `.env` view plus
backup/rollback), **Logs** (pick a component, then a pod, then tail it),
**Kubernetes Dashboard** (generate a 1-hour view-only or administrator
access token), **URLs & Credentials** (service URLs, short login guidance,
and an opt-in check of whether a credential is present -- never its
value), **Certificates & Trust** (the mkcert root CA path and lab
hostnames to import it for), **Diagnostics** (run the read-only collector
and write a sanitized bundle), **Runbooks** (safe previews of the
first-scan, backup, and troubleshooting topics), **Tools** (Flight Plans:
list the catalog and compare a plan's components against the current
`.env`), and **Help** (the offline Help Center topics). The mutating
screens (Deploy, Applications,
Configuration, Kubernetes Dashboard) preview dry-run by default and
require pressing `a` to arm real execution before `enter` (or, on
Kubernetes Dashboard, `m`) runs anything against your cluster — the same
posture as the Bash wizard, except the Dashboard's view-only token, which
generates immediately with no arming, matching Bash's own no-confirm
behavior for that option; Diagnostics, Runbooks, Tools, and Help are
read-only and have no arming step at all. Destroy actions and free-text
`.env` editing stay Bash-wizard-only for now: both need a typed
confirmation phrase or a key/value the TUI has no text-entry widget for
yet. Persistent (non-expiring) Dashboard tokens stay Bash-wizard-only for
the same reason -- Bash requires typing the literal word `PERSISTENT` for
those. Promoting a Flight Plan candidate, applying one (writes `.env`),
and Docker Hub discovery also stay Bash-wizard-only, same reason. Revealing
an actual credential value from URLs & Credentials stays Bash-wizard-only
too -- Bash requires typing the literal word `REVEAL` first. Generating or
regenerating TLS artifacts, bringing your own certificate and key, staging
a root CA export, and staging fcli trust configuration also stay
Bash-wizard-only -- Certificates & Trust is display-only. The Dashboard's
TLS-artifacts check only confirms the files exist and are non-empty; it
does not cryptographically validate them the way Bash's `certs_ready()`
does (that runs `openssl`/`keytool` against the private key and keystore
password), and it offers no repair action -- same as Bash, fixing a
`warn` item happens elsewhere in the wizard. The fcli
activation/trust-import lifecycle also stays Bash-wizard-only,
deliberately not yet ported (see the roadmap). Deploy / Resume's step
statuses are color-coded (green/yellow/red/cyan, matching Bash's own
status board with one addition -- see below), dry-run now visibly walks
through each pending step's preview
in turn, and a real step shows `running` immediately instead of freezing
the whole screen until it finishes (it runs on a background thread; the
TUI's event loop now wakes up periodically even with no keypress, so the
result gets picked up and rendered as soon as it's ready) -- but it still
can't detect a step that's already deployed from outside this screen (a
prior session, or the Bash wizard); every step starts `pending` until
Deploy / Resume itself runs it. Bash's equivalent
live-state detection (`certs_ready`, `ssc_ready`, etc.) does several
kubectl probes per step and isn't ported yet (see the roadmap). A
`running` step now also gets its own color (cyan) instead of sharing
`pending`'s yellow -- the two used to look identical at a glance, which
read as "is this stuck?" -- and once armed, Deploy / Resume drives the
*whole* remaining plan forward automatically (one confirmation, then
unattended until done or a step fails, matching Bash's own guided
auto-advance) instead of needing `a` pressed again before every single
step.
Applications got the same two fixes: starting SSC/LIM/MySQL/PostgreSQL
used to fail every time with a permission error (scripts invoked
directly instead of via `bash`), and a real start/stop now shows
`(running...)` instead of freezing the screen. Logs now reads the
namespace from `.env`'s `NAMESPACE` instead of a hardcoded `fortify` for
both listing pods and tailing them. Flight Plans no longer flags a
customized MySQL/PostgreSQL version as plan "drift" -- Bash never counts
those, and now neither does this screen. The Lab Status Dashboard's root
CA and fcli truststore checks were reading the wrong `.env` keys and are
now aligned with Bash's actual fallback logic.

Applications and Lab Lifecycle then got a deeper pass specifically on
deployment/individual-component management. Applications is now two
levels, matching Bash's `apps_menu()`/`app_action_menu()` shape: pick an
app from the live-status list, then Start/Upgrade, Stop, Logs (jumps
straight into the Logs screen pre-filtered to that app), or Show URL &
credentials (inline, not a duplicate of the URLs & Credentials screen --
just its per-app subset), or Destroy, gated by typing the exact
confirmation phrase Bash requires (e.g. `DESTROY ssc`) into a new
`TextField` text-entry widget -- the piece every typed-confirmation gap
in this migration had been waiting on. Lab Lifecycle is new: the
non-destructive quarter of Bash's `lab_lifecycle_menu()` (shutdown/start,
scoped to the active profile or the whole lab), built by handing an
ordered sequence of app operations to the same
`DeployService`/`GuidedDeployScreen` Guided Deploy already uses -- so the
color-coding, dry-run-cycling, and running-indicator behavior apply
automatically, no separate implementation to keep in sync. ScanCentral
SAST and DAST are in the Applications app list too, each as one combined
row over Bash's controller+sensor/core+scanner pair (DAST's start/stop
chains its two scripts the same way Bash's `run_app_scripts()` does,
aborting on the first failure). Scale workers is wired up too, for
SAST/DAST only, matching Bash's `scale_workers()`: offered in the same
per-app menu for every app, showing the current replica count and a
`TextField` prompt for a new one -- empty cancels, a non-digit value is
rejected with "Not a number" and no `kubectl scale` call, and any other
app gets the same "Scaling not supported" result Bash's own case
statement produces. Lab Lifecycle's own destroy/reset quarter, credential
`REVEAL`, Dashboard's `PERSISTENT` tokens, and per-key `.env` editing all
still need their own screen-specific wiring onto the text-entry widget --
each needs its own validation shape (a different confirmation phrase, an
arbitrary value), not just a `TextField`.

`./start_wizard.sh` also has an opt-in hook: set `FORTIFY_PYTHON_TUI_PREVIEW=1`
and it execs into the Python TUI above (after the same acknowledgement,
env bootstrap, and fcli activation every run already does) instead of
entering the Bash menu. It's a preview, not the default — leave the
variable unset and `start_wizard.sh` behaves exactly as before.

Install `requirements-python.txt` only if you're developing or previewing
those CLI/TUI slices (kept separate from `requirements-docs.txt`, which is
for building the documentation site):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-python.txt
```

## Using the wizard

The main menu opens on a small **Essentials** screen (Deploy, Lab lifecycle
controls, Configuration editor, Logs, and a first-scan one-click demo once
SSC and ScanCentral SAST are up), a **`?`** hotkey straight to the Help
Center from anywhere on that screen, and **m. More tools** for everything
else, organized by task: Deploy, Diagnostics and advanced, Operations, and
Learn (an offline Help Center with guides to every component, answerable even
when the cluster is down).

- **Guided deployment (recommended)** — a numbered, explanatory walkthrough
  with a deployment-profile picker (SSC only, SAST, DAST, Full lab, sample
  apps, or Custom).
- **Express deployment** — the same underlying operations, run unattended
  back-to-back.
- **Resume or repair** — after a failure or safe quit, picks up at the first
  incomplete step; never persists passwords or tokens.
- **Deployment Versions and Flight Plan** — pick, preview, upgrade, or
  compare component-version bundles; see [Versions and
  compatibility](docs/operations/versions-and-compatibility.md).

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
start_wizard.sh           Interactive launcher.
setup.sh                  One-shot bootstrap (delegates to the wizard).
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

- **Run as your normal user**, never `sudo ./start_wizard.sh`. mkcert is
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
./start_wizard.sh
# Apps → each app → Destroy
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

For deployment errors, use **Operational guidance → Create sanitized diagnostics bundle**,
inspect the allow-listed archive locally, and include only that minimum
evidence plus the failed wizard step. Do not attach raw logs, `.env`, Secret
values, license data, tokens, or private keys.

Questions or ideas: open a [GitHub issue](https://github.com/treisland/fortifylab/issues).

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for notable changes by release.

## License

MIT. See [`LICENSE`](LICENSE).
