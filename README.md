# Fortify Lab on Kubernetes

A scripted Fortify deployment for evaluation, training, and demos:
**SSC**, **ScanCentral SAST**, **ScanCentral DAST**, **LIM**, plus the
Kubernetes Dashboard, all running on [microk8s](https://microk8s.io/) with
mkcert-issued TLS. Every step driven by an interactive wizard or a single
"deploy from scratch" command.

> Not a production deployment guide — opinionated defaults, single-node
> cluster, NFS PVCs. Intended for lab and evaluation use.

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

## Prerequisites

- Linux host (Ubuntu 22.04+ tested)
- ~16 GB RAM, ~50 GB disk free
- Browser reachability to the host (LAN IP, public IP, or VPN)
- A Fortify license (`fortify.license`), stored outside the repository when
  desired — see [`secrets/input/README.md`](secrets/input/README.md)
- A Docker Hub login that can pull from `fortifydocker/*` and `bitnamilegacy/*`

## Quick start

```bash
git clone https://github.com/treisland/fortifylab.git
cd fortifylab
cp .env.example .env
# Edit .env: at minimum set DOMAIN, DEFAULT_PASS, FORTIFY_LICENSE_FILE,
# and check image versions. The repository-local license default still works.
./start_wizard.sh
```

The first launch displays a mandatory **LAB / DEMO USE ONLY** notice. Type
`LAB` to acknowledge that this repository's single-node architecture and
automation are not production supported. This limitation applies to this
deployment toolkit, not to the production capabilities of Fortify products.
See [`docs/lab-use.md`](docs/lab-use.md). A concise lab-mode banner remains
visible in the wizard after acknowledgement.

Inside the wizard, the main menu is organized by task:

- **Deploy:** Guided deployment, Express deployment, Resume or repair,
  individual component management, and Kubernetes Dashboard access.
- **Diagnostics and advanced:** live status plus the advanced setup menu for
  prerequisites, license files, certificates/secrets, DNS, SSC token, LIM,
  Dashboard access, and `.env` editing.
- **Operations:** lab lifecycle controls, logs, cluster snapshot, one-pod logs,
  URLs and credentials, image versions, Configuration editor, and wizard log.
- **Learn:** the Help Center / Fortify Knowledge Center and operational
  guidance.

Choose **Guided deployment (recommended)** for a numbered, explanatory
walkthrough. Guided deployment first asks for a deployment profile: SSC only,
SAST controller only, SAST full with SSC, DAST full, Full lab, or Custom. The
wizard expands required dependencies before it shows the final plan. Each screen
shows status derived from current files and live Kubernetes resources. Required
steps cannot be skipped; optional host setup and post-deploy configuration can
be deferred. Guided wait screens poll through readiness and application checks,
show recent relevant events, and let you open contextual pod logs or live
diagnostics without leaving the guided flow. Interactive mode pauses after each
verified step; auto-advance continues after a 5-second countdown unless you take
control.

Choose **Express deployment** for the original unattended sequence: certs →
Kubernetes Dashboard → secrets → MySQL + Postgres → SSC + LIM → SAST → DAST.
Guided and Express modes call the same underlying component operations and
dependency gates; Guided adds selectable profiles and orchestration around those
operations.

Choose **Resume or repair** after a failure or safe quit. It locates the first
incomplete required step from Kubernetes and generated files. The wizard does
not create a state file and never persists passwords or tokens. Use **Manage
individual components (expert) → Start / Upgrade** when intentionally repairing
one component.

Choose **Help Center / Fortify Knowledge Center** for offline, read-only guides
to the system, each Fortify and database component, dependency/data flow,
interfaces, roles, and terminology. Guided deployment screens also accept `?`
to open help for the current step. The Help Center reads committed text under
`docs/help/` and remains available when MicroK8s is offline.

Long-form documentation is maintained as code under `docs/`; see the
[documentation architecture decision](docs/adr/0001-mkdocs-authoritative-documentation.md)
for the source-of-truth, offline-help, publishing, and GitHub Wiki boundaries.

Choose **Operational guidance and troubleshooting** for a read-only environment
overview, deployment plan, unfinished-work summary, symptom-driven guidance,
network/TLS and lifecycle explanations, compatibility notes, backup/recovery
guidance, and the synthetic [first-scan walkthrough](docs/operations/first-scan.md).
It can also create a deliberately minimal diagnostics archive in the user's
private state directory. Review every archive before sharing it; the bundle
excludes logs, Secret and ConfigMap data, environment variables, command lines,
license metadata, credentials, and local configuration paths.

The Dashboard is surfaced before application workloads so it can monitor the
rest of the deployment. After deployment, use **URLs & credentials** to print
configured URLs and login guidance without disclosing stored passwords or
tokens.

If a guided operation fails, its screen remains incomplete and offers Retry.
Fix the reported dependency, retry the same operation, or quit safely and use
Resume later. Rendering status performs read-only file and Kubernetes queries;
it never installs, upgrades, generates credentials, or rotates TLS material.

The Dashboard is the lab's operational Web UI. Open
`https://dashboard.$DOMAIN`, then use **Kubernetes Dashboard access** from the
main menu, or **Advanced setup and configuration → Configure DNS, SSC token,
LIM, and Dashboard access → Kubernetes Dashboard access**, to generate a
one-hour token. Choose view-only access for routine monitoring. Administrator
access is offered separately with a warning because it can modify or delete
every workload, Secret, and persistent resource in the cluster. Tokens are
neither stored by this repository nor printed during deployment; the wizard
prints one only after an explicit operator request. Persistent view-only and
administrator tokens are also available for isolated labs. They are stored only
in Kubernetes, remain valid until revoked, and can be revoked from the same
Dashboard access menu. Prefer one-hour tokens whenever practical.

The fresh/express deployment path refuses to run over existing managed Helm
releases. Use **Guided deployment** or **Resume or repair** for an existing lab;
use **Apps → Start / Upgrade** when intentionally repairing one component. This
protects persistent data, SSC encryption material, and application credentials
from accidental reset.

### Dependency gates and safe retries

The wizard checks authoritative dependencies before it starts a consumer, in
both **Deploy from scratch** and **Apps → Start / Upgrade**:

- SSC waits for the MySQL StatefulSet and an authenticated `SELECT 1`.
- ScanCentral SAST controller can be deployed independently for standalone SAST.
- ScanCentral SAST sensor waits for the SAST controller; the SAST full profile
  also includes SSC and MySQL for the integrated lab workflow.
- DAST Core waits for an authenticated PostgreSQL query, SSC, and LIM in the
  current lab topology.
- The DAST scanner waits for all DAST Core workloads and its API endpoint.

Every wait is bounded by `FORTIFY_HEALTH_TIMEOUT` (600 seconds by default).
Failures print only the dependency name and a safe remediation; passwords,
query output, and HTTP response bodies are suppressed. A failed gate makes no
change to the dependent component. Correct the unhealthy dependency and rerun
the same Start / Upgrade action; completed dependencies are detected and the
operation continues normally.

Application probes route the configured TLS hostname to the local ingress, so
fresh deployment does not require client DNS to be configured first. HTTP
success, redirect, authentication, and other non-server-error responses count
as an answering application; connection failures and HTTP 5xx responses do not.

## DNS setup

The lab issues TLS certs for the wildcard `*.$DOMAIN` (default
`fortifydemo.com`). Browsers and pods both need to resolve those hosts to
the cluster's node IP.

**Client-side** (your laptop) — add to `/etc/hosts` (or Pi-hole):

```
<host-ip>  ssc.fortifydemo.com sast.fortifydemo.com dast.fortifydemo.com lim.fortifydemo.com dashboard.fortifydemo.com
```

**In-cluster** — pods also need the lab hostnames to resolve to the node so
service-to-ingress traffic keeps the expected Host header. The wizard's
**Advanced setup and configuration → Configure DNS, SSC token, LIM, and
Dashboard access → DNS** option patches CoreDNS's hosts plugin so SCDAST
scanner ↔ DAST API and SAST ↔ SSC traffic resolves correctly.

## TLS trust

`scripts/create-certs.sh` uses [mkcert](https://github.com/FiloSottile/mkcert)
to create a per-machine root CA and a wildcard leaf for `*.$DOMAIN`. To
make your browser trust the lab:

```bash
# From your laptop:
scp ubuntu@<host>:~/fortifylab/certs/rootCA.pem ~/Downloads/fortify-rootCA.pem

# macOS: open Keychain Access → System keychain → drag in rootCA.pem →
#        double-click → set "Always Trust"
# Linux: sudo cp ~/Downloads/fortify-rootCA.pem /usr/local/share/ca-certificates/fortify-rootCA.crt
#        sudo update-ca-certificates
# Firefox: about:preferences#privacy → Certificates → import as authority
```

Re-running `create-certs.sh` rotates the root CA — you'll need to
re-import. The wizard does not warn you about this; treat it as a
fresh-install operation.

The same DNS and TLS trust setup applies to Dashboard, SSC, LIM, SAST, and
DAST. MicroK8s 1.35+ uses Traefik for the `ingress` addon;
`scripts/create-secrets.sh` now points MicroK8s ingress at the mkcert wildcard
Secret `fortify/tls` so browsers receive the lab certificate instead of
`TRAEFIK DEFAULT CERT`. The application start scripts also add Traefik backend
service annotations for HTTPS services with lab-generated internal
certificates. If a browser still reports `TRAEFIK DEFAULT CERT`, rerun the
Secrets step or run:

```bash
microk8s enable ingress --default-ssl-certificate fortify/tls
```

Then recheck the hostname with `openssl s_client -servername`. If the browser
reports a name or certificate error after that, verify the client hosts/DNS
entry and import this lab's `certs/rootCA.pem` before generating a Dashboard
token or logging into SSC.

## Manual configuration after deploy

Two steps still need a human after `Deploy from scratch`:

- **SSC ControllerToken**: Log into SSC → Administration → ScanCentral SAST
  → Tokens → create a token of type `ScanCentralCtrlToken`. Run wizard
  Configure → option 2 to enter it through hidden input. The wizard patches the
  existing Kubernetes Secret through standard input and restarts the controller;
  the token is not placed in files, Helm values, or process arguments. This
  operation also clears token material left in Helm metadata by older versions
  of the wizard.
- **DAST license + pool in LIM**: Open `https://lim.$DOMAIN`, sign in with
  `lim_admin` username and configured lab password, upload the
  DAST license file, create a pool named `Default` (matches `LIM_POOL_NAME`
  in `.env`), then redeploy ScanCentral DAST so the scanner can authenticate.

## Repo layout

```
.env.example              Template — copy to .env, edit DOMAIN/passwords/versions.
start_wizard.sh           Interactive launcher.
setup.sh                  One-shot bootstrap (delegates to the wizard).
scripts/
  create-certs.sh         mkcert root + leaf, JKS keystore, JVM truststore.
  create-secrets.sh       k8s Secrets: explicit per-key, no folder dump.
  install_microk8s.sh     microk8s + addons.
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

## Cleanup

```bash
./start_wizard.sh
# Apps → each app → Destroy
# Then on the host:
microk8s helm -n fortify list                     # confirm none remain
microk8s kubectl delete namespace fortify         # nuke everything else
```

## Contributing

PRs welcome. For deployment errors, use **Operational guidance → Create
sanitized diagnostics bundle**, inspect the allow-listed archive locally, and
include only that minimum evidence plus the failed wizard step. Do not attach
raw logs, `.env`, Secret values, license data, tokens, or private keys.

## License

MIT. See [`LICENSE`](LICENSE).
