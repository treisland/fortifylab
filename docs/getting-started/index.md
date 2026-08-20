# Get from zero to a running lab

This is the shortest safe path for a new operator to clone the repository,
deploy the tested single-node lab, and reach its user interfaces. The wizard
does the installation work; this page explains what it checks and changes.

!!! danger "Lab and demo use only"

    Use synthetic source, targets, credentials, and scan results. This toolkit
    is an opinionated single-node learning environment, not a production
    deployment guide. Read the [lab-use boundary](../lab-use.md) before you
    expose the host to a network.

## Before you begin

Use a dedicated Ubuntu 22.04-or-newer Linux host on which you can run `sudo`.
The tested profile needs at least **16 GiB RAM** and **50 GiB free disk**.
Deployment also needs:

- a browser that can reach the host by its LAN address, public address, or VPN;
- a Fortify license file that is readable by your normal user;
- a Docker Hub account entitled to pull `fortifydocker/*` and
  `bitnamilegacy/*` images; and
- outbound access for Ubuntu packages, snaps, container images, Helm charts,
  and Fortify update services.

Allow **15–20 minutes for Express deployment after prerequisites and images
are available**. A first run on a new host commonly takes **30–60 minutes**
because package installation, image downloads, SSC database migration, and
network speed vary. Guided mode displays an estimate for each step.

The deployment installs host packages and MicroK8s add-ons, creates a local
certificate authority, writes generated material under this checkout, creates
Kubernetes Secrets, allocates persistent volumes, and applies workloads and
ingress resources. Run the wizard as your normal user, not with `sudo`; it asks
for elevation only where host installation requires it.

## 1. Clone and prepare configuration

```bash
git clone https://github.com/treisland/fortifylab.git
cd fortifylab
cp .env.example .env
${EDITOR:-nano} .env
```

At minimum, replace the example passwords, choose `DOMAIN`, and review the
pinned chart and image versions. Keep `.env` private and do not reuse lab
credentials elsewhere.

Set `FORTIFY_LICENSE_FILE` to an absolute path outside the repository when
possible:

```bash
export FORTIFY_LICENSE_FILE="/srv/fortify-lab-private/fortify.license"
```

Put that assignment in `.env` if it should persist between wizard runs. The
backward-compatible default, `secrets/input/fortify.license`, is gitignored,
but an external protected directory makes the repository boundary clearer.
The wizard checks only that the configured file is readable and non-empty; it
does not print the path or contents. See [Secrets and licenses](../operations/secrets-and-licenses.md).

## 2. Start the wizard

```bash
./start_wizard.sh
```

On first use, the wizard shows a Fortify Lab welcome banner with the current version,
then asks you to read the **LAB / DEMO USE ONLY** notice and type `LAB` to
acknowledge it. The next screen is a beginner-oriented welcome page with the
recommended path, a short component map, warnings, important local file
locations, and a read-only snapshot of `.env`, license, Docker, MicroK8s,
domain, and deployment profile. Use it to confirm where generated files and
logs live before you deploy. From there, start Guided deployment or continue to
the main menu.

From the main menu, choose **1. Deploy**, then pick one deployment mode:

=== "Guided (recommended)"

    Choose **1. Guided deployment**. First choose the deployment profile you
    want: SSC only, SAST controller only, SAST full with SSC, DAST full, Full
    lab, or Custom. The wizard expands required dependencies and shows the active
    plan before you choose interactive or auto-advance mode. It then shows one
    numbered step at a time, including current status, expected duration, and
    mutation impact. Required steps cannot be skipped. Enter `?` for contextual
    help, or quit safely and return later.

    The guided flow is expected to wait through lifecycle verification after
    each operation. While work is still starting, the wait screen should show
    gradual readiness updates instead of requiring repeated menu refreshes.
    Interactive mode pauses after a verified step; auto-advance mode continues
    after a 5-second countdown unless you take control.

    The prerequisite screen shows readiness indicators for JDK, Docker login,
    mkcert, and MicroK8s access. When MicroK8s is installed but the current
    shell has not picked up the `microk8s` group yet, choose `g` from that
    screen to restart the wizard with group access, or run `newgrp microk8s`
    before relaunching. Guided step and wait screens include Retry, Help, live
    diagnostics, diagnostics bundle export, interactive takeover, and
    contextual pod logs where a component owns pods. On completion, Guided
    shows a congratulations page with live service status, URLs, certificate
    trust guidance, recommended manual next steps, the wizard log, and the
    access-and-credentials handoff.

=== "Express"

    Choose **2. Express deployment** after you understand the plan. It runs the
    same operations and dependency gates without pausing between successful
    steps. It is not a less-safe or separate installer.

The full-lab path runs in this order:

1. host prerequisites and read-only deployment preflight;
2. lab TLS certificates and Kubernetes Dashboard;
3. Kubernetes Secrets;
4. MySQL and PostgreSQL;
5. SSC and LIM;
6. ScanCentral SAST controller and sensor;
7. ScanCentral DAST Core and scanner; and
8. optional post-deployment configuration.

Smaller Guided profiles omit the unselected application branches while keeping
shared platform setup, TLS, secrets, and required dependencies. Profile changes
never stop or remove existing resources; use lifecycle controls or component
Destroy only when that is intended.

The preflight verifies the license, required commands, MicroK8s, the `nfs`
storage class, registry login, required settings, memory, and free disk. It is
read-only and can run during resume/repair. The fresh/express deployment path
refuses to continue if managed Helm releases already exist; Guided deployment
routes existing labs to **Resume or repair** automatically.

!!! important "SSC cannot outrun MySQL"

    The wizard starts MySQL first, waits for its StatefulSet, and requires a
    successful authenticated `SELECT 1` before it starts SSC. SSC database
    migrations never begin merely because a MySQL pod exists. The wait is
    bounded by `FORTIFY_HEALTH_TIMEOUT` (600 seconds by default). If it fails,
    SSC is not changed: repair MySQL and retry the SSC step.

PostgreSQL has the equivalent authenticated gate for DAST. The SAST controller
can run without SSC, SAST sensors require the controller, and the SAST full
profile adds SSC/MySQL for the integrated workflow. DAST waits for PostgreSQL,
SSC, and LIM in this lab topology. These checks explain why repairing the first
unhealthy dependency is more useful than restarting every pod.

## 3. Resume or repair safely

If a step fails, read its named dependency and correct that condition. Then
retry the same Guided step, or quit and later choose **1. Deploy → 3. Resume
or repair deployment**. Resume inspects current files and live Kubernetes resources,
starts at the first incomplete required step, and does not store a separate
progress file, password, or token.

Completed work remains in place. A retry can update the resources owned by
that step, but it does not implicitly delete persistent data. For an existing
component, use **Manage individual components → Start / Upgrade** only after
reviewing the configured versions and backup implications.

Useful read-only checks are available from **Diagnostics / live status**,
**Cluster snapshot**, and the [troubleshooting guide](../troubleshooting/index.md).
Do not delete PVCs, rotate credentials, regenerate TLS, or replace SSC
`secret.key` as a generic repair attempt.

## 4. Configure browser and in-cluster DNS

The configured domain produces these names:

```text
ssc.<domain> sast.<domain> dast.<domain> lim.<domain> dashboard.<domain>
```

Point all five names at the lab node in your client DNS, or add one line to the
client hosts file using the node address that the browser can reach:

```text
<lab-node-ip>  ssc.<domain> sast.<domain> dast.<domain> lim.<domain> dashboard.<domain>
```

Then choose **Advanced setup and configuration → Configure DNS, SSC token,
LIM, and Dashboard access → DNS**. With confirmation, this patches CoreDNS so
pods can resolve the same hostnames through ingress. The wizard prints the
client entry but cannot change your laptop's DNS or hosts file.

Import the public `certs/rootCA.pem` into the trust store of a dedicated lab
client. Never bypass TLS verification. Regenerating certificates rotates the
lab CA and requires clients to trust the replacement. The Secrets step creates
the Kubernetes `fortify/tls` Secret from the mkcert wildcard leaf and, on
Traefik-backed MicroK8s ingress, sets it as the default frontend certificate so
Dashboard and SSC do not present `TRAEFIK DEFAULT CERT`. Follow
[Networking, URLs, and TLS](../operations/networking-and-tls.md) for platform-specific guidance.

## 5. Open Kubernetes Dashboard

Open `https://dashboard.<domain>`, then choose **m. More tools → 7. Kubernetes
Dashboard access** in the main menu. The same workflow is also available under
**Advanced setup and configuration → Configure DNS, SSC token, LIM, and
Dashboard access**:

| Choice | Use | Lifetime and risk |
|---|---|---|
| One-hour view-only | Routine monitoring | Recommended; expires after one hour |
| One-hour administrator | A bounded administrative task | Full cluster control until expiry |
| Persistent view-only | Isolated lab where repeated login is necessary | Does not expire automatically |
| Persistent administrator | Exceptional isolated-lab administration | Full cluster control until revoked |

The wizard repairs missing Dashboard access resources before token generation.
It prints a token only after an explicit request and does not persist it in the
repository. Treat every token as a bearer credential; never commit, log, or
send it in chat.

Persistent tokens are Kubernetes Secrets and remain valid until revoked.
Return to **Kubernetes Dashboard access → Revoke persistent Dashboard tokens**
when they are no longer needed. Revocation removes both persistent token
Secrets but does not revoke already issued one-hour tokens. Prefer view-only,
one-hour access for normal observation. Administrator access can read Secrets
and modify or delete every workload and persistent resource.

## 6. Finish application configuration

Use **12. URLs & credentials** to print configured URLs, safe login guidance,
credential availability, retrieval commands, certificate trust instructions, and
an explicit reveal-one-credential flow. Raw passwords and tokens are hidden by
default and are never written to wizard logs, diagnostics, `.env`, or generated
summary files by that screen.

Two application tasks still require a person:

1. Open SSC as `admin`; refer to the SSC documentation for the default
   administrator password. In SSC, create a token of type
   `ScanCentralCtrlToken`; then choose **Advanced setup and configuration →
   Configure → Apply SSC ControllerToken**. Input is hidden and the wizard
   updates the protected Secret without putting the token in files, command
   arguments, or Helm values.
2. Open LIM as `lim_admin`, retrieve the password from **URLs & credentials**
   if needed, upload the entitled ScanCentral DAST and WebInspect licenses, and
   create the pool named by `LIM_POOL_NAME` (default `Default`). Then run
   **Manage individual components → ScanCentral DAST → Start / Upgrade** so the
   scanner can authenticate to LIM.

Confirm that MySQL, SSC, and the SAST controller and worker are healthy before
following the [first successful scan](../operations/first-scan.md) walkthrough.
The completion screen also offers a **First scan handoff** that points to
placeholder SAST/DAST command starters under `docs/examples/first-scan/`.
Those starters keep SSC as the primary result destination, keep FoD optional,
and require tokens and target URLs through environment variables.

## Destructive actions are separate

Stopping a component retains its persistent data. Resume and ordinary retries
do not delete data. Destruction is available only under the expert component
menu, is labelled **Destroy (deletes data)**, repeats the lab safety warning,
and asks for confirmation.

!!! danger "Back up before destruction or upgrades"

    Destroy can delete application resources and persistent data. Do not use it
    to repair an unhealthy pod. Back up databases with their matching state—
    especially the SSC database together with SSC `secret.key`—and review the
    [backup and recovery](../operations/backup-and-recovery.md) and
    [lifecycle](../operations/deployment-and-lifecycle.md) guidance first.
