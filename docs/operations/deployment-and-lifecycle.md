# Deployment, resume, and lifecycle safety

Use `./start_wizard.sh` as your normal user. Guided deployment lets the operator
choose a deployment profile, expands required dependencies, previews the active
plan, and resumes at the first missing layer:

1. host prerequisites and MicroK8s;
2. lab TLS certificates;
3. Kubernetes Dashboard;
4. Kubernetes Secrets;
5. MySQL and PostgreSQL;
6. SSC and LIM when selected;
7. ScanCentral SAST controller, then sensor when selected;
8. ScanCentral DAST Core when selected;
9. ScanCentral DAST scanner when selected;
10. client DNS/TLS trust and a synthetic scan.

The unfinished-work summary reports resource **presence**, not readiness or
application health. A safe resume checks the first missing item, then verifies
each existing dependency with the layered health gates before continuing.

## Operation semantics

| Operation | Intended effect | Persistent data |
|---|---|---|
| Start / Upgrade | Helm upgrade/install, scale up, then verify dependencies | retained |
| Stop | scale application StatefulSets to zero | retained |
| Restart | stop then start after dependencies are healthy | retained |
| Repair / retry | rerun an idempotent failed step after fixing its dependency | retained |
| Uninstall release | remove the named Helm release/resources | script-dependent; review first |
| Delete data | explicitly remove persistent claims | permanently deleted |

!!! danger "Destroy in the current wizard deletes data"
    The component menu labels action 3 **Destroy (deletes data)**. Some current
    destroy scripts remove only the Helm release, while database and LIM
    destroy scripts also delete their claims. Treat every Destroy action as
    destructive and confirm only when loss of that component's lab data is
    intended. Stop is the safe choice when data must remain.

## Safe start and resume

1. Preview **Operational guidance → Deployment plan**.
2. Use Guided or Resume/repair for an existing lab; fresh/express deployment is
   reserved for a lab without managed releases.
3. Use the unfinished-work summary only to find missing resources.
4. Establish storage and database health before application consumers.
5. Start consumers in the dependency order above. SSC waits for MySQL; the SAST
   sensor waits for the SAST controller; the SAST full profile also adds SSC and
   MySQL; DAST Core waits for PostgreSQL, SSC, and LIM in the current lab
   topology; the DAST scanner waits for Core.
6. Wait for bounded application-health success, not just `Running` pods.
7. If a step fails, fix its first unhealthy dependency and retry that same
   step. Completed Helm steps are designed to be detected or upgraded again.

## Safe stop

Stop in reverse dependency order so consumers cannot continue writing through
services that are disappearing:

1. DAST scanner, then DAST Core;
2. ScanCentral SAST workers/controller;
3. SSC and LIM;
4. MySQL and PostgreSQL last.

The component Stop scripts scale workloads to zero and retain claims. Confirm
zero replicas and leave the namespace, Secrets, and PVCs in place.

## Safe restart and repair

Restart one dependency branch at a time. Stop the affected consumers in reverse
order, repair or restart the earliest dependency, verify its application
health, then start consumers in forward order. A restart is not a fix for
corrupt data, incompatible migrations, missing entitlements, or incorrect TLS
trust.

Do not rotate database passwords, SSC `secret.key`, controller/service tokens,
or the mkcert trust root as incidental repair. Re-running certificate creation
rotates trust and requires dedicated clients to import the new public CA.

## Guided deployment orchestration contract

Guided deployment should behave like a small orchestrator around the component
scripts. A script returning success means the operation was launched or applied;
the guided step is not complete until its lifecycle verification passes.

Each guided step has these lifecycle states:

| State | Meaning |
|---|---|
| Pending | Required inputs or resources are not present yet |
| Running | The component operation is being applied |
| Verifying | The wizard is polling readiness and application-health probes |
| Complete | The step-specific completion probe has passed |
| Failed | The operation or verification timed out and needs operator action |
| Skipped | An optional step was deliberately deferred |

The live wait screen updates gradually while a step is Running or Verifying. It
shows elapsed time, timeout, current probe name, workload readiness counts,
recent relevant Kubernetes events when available, and safe controls for Retry,
Help, live diagnostics, diagnostics bundle export, interactive takeover,
contextual pod logs, and safe quit.
Status rendering remains read-only: it may inspect files and Kubernetes
resources, but it must not install packages, apply manifests, create secrets,
rotate TLS, or delete data.

Guided mode supports selectable deployment profiles. The built-in profiles are
SSC only, SAST controller only, SAST full with SSC, DAST full, Full lab, and
Custom. Custom selections are stored as non-secret `.env` settings only when the
operator chooses to save them; otherwise they apply to the current wizard session.
Changing a profile does not stop or delete resources that already exist.

Guided mode supports two operator styles:

- **Interactive** pauses after each successful verification and lets the
  operator choose the next step.
- **Auto-advance** runs the same lifecycle and verification gates, then shows a
  countdown before continuing to the next step. During the countdown, the
  operator can take control and return to interactive mode without killing
  already-completed work.

Resume and failure handling are derived from live state, not from a stored
wizard progress file. If a previous operation created resources that are still
starting, Resume should identify the first incomplete required step and enter
the same verification wait instead of blindly rerunning the command. If a step
fails or times out, the wizard should name the failed probe, show live
diagnostics, offer contextual pod logs, keep sanitized diagnostics bundle export
separate, and offer Retry, Help, interactive control, or safe quit.

The shell implementation exposes stable hooks for this contract:

- `guided_apply_deployment_profile`
- `guided_step_probe`
- `guided_step_timeout`
- `guided_step_in_progress`
- `guided_wait_for_step`
- `guided_run_and_verify`
- `guided_countdown`
- `guided_live_diagnostics`
- `guided_diagnostics_bundle`

## Uninstall versus data deletion

The repository does not yet expose a uniform retain-data uninstall action.
Inspect the named script before using Destroy:

- MySQL, PostgreSQL, and LIM destroy scripts delete their PVCs.
- SSC, SAST, and DAST destroy scripts remove their Helm releases; associated
  shared data and Secrets require separate review.
- Deleting the `fortify` namespace removes namespaced resources broadly and is
  a full-lab destructive reset, not routine cleanup.

Before any destructive action, identify the exact release and claims, create
the required recovery artifacts, and verify the confirmation names the data to
be lost. Never use PVC deletion as routine repair.

## Upgrade boundary

This lab is not a production upgrade system. Compare configured chart, image,
product, and database versions; take application-consistent exports; preserve
the matching SSC `secret.key`; and read vendor release notes. Helm rollback can
restore manifests but cannot reverse a database migration. Prove recovery in
an isolated lab before relying on it.
