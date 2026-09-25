# Changelog

All notable changes to FortifyLab are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Flight Plan redeploys: after a Flight Plan change the wizard detects which
  deployed products run a chart or image other than `.env`, marks them
  **needs redeploy** in the guided deployment, and offers to redeploy only
  those, in dependency order. `apply-flight-plan --redeploy` does the same
  non-interactively.
- Deployed Flight Plan banner above every wizard screen: selected versus
  running plan, products that need a redeploy, and when it was checked.
- `./start_wizard.sh flight-plan-status` and a **Show deployed vs configured
  versions** menu item.
- `flight-plans.py relation` and `match-running` commands.

### Changed

- Downgrading to an older Flight Plan release family now requires typing the
  plan id interactively, or `--allow-downgrade` with `apply-flight-plan --yes`.
- A product's release overlay now follows its own chart version when `.env`
  overrides it away from the selected Flight Plan.
- Promoting a candidate keeps extra plan fields, and `show` marks local plans
  that override a curated plan.

### Fixed

- Deploy verification waited only for replica counts, so a redeploy could be
  verified against the previous pod. StatefulSets must now finish their rollout.
- Applying a full Flight Plan now clears stale component drift markers.
- Release discovery no longer matches family `25` to tags such as `250.1`.
- Flight Plan tests no longer pick up local catalogs, `.env` backups, or a
  live cluster from the developer machine.

## [0.2.0] - 2026-08-21

### Added

- Fortify Flight Plans: curated version bundles with discovery, preview,
  promote-to-local, and upgrade workflows, plus release-aware deployment
  overlays.
- First-scan one-click demo (SAST/IWA-Java): submits a real ScanCentral SAST
  scan and reports severity results, built on a reusable scan-type
  abstraction so DAST/SCA can reuse the same shape later.
- Runbook Library v1, and a Python CLI/TUI operator console foundation.
- Bring-your-own TLS support and advanced coordinated multi-node cluster
  profiles.
- Guided setup readiness flow and TLS maturity checks.
- First-scan demo prerequisites: Maven check, inline fcli install offer, and
  a Fortify Security Content rulepack presence check.
- First-scan demo results: a direct SSC web UI link and timestamped
  scan-status polling.
- `Maven` added to the wizard's `Install prerequisites` menu, alongside
  JDK/Docker/mkcert/microk8s.

### Changed

- Modularized the Bash wizard architecture.
- Restyled the docs site with an OpenText-inspired palette; restructured the
  README for beginners.
- Grouped the Deployment Versions menu under section headers and moved
  discovery ahead of advanced options; numbered status selection for "Add to
  my local Flight Plans".
- The guided wizard's completion screen now hands off to the real first-scan
  demo instead of generating placeholder starter scripts.
- fcli now uses its own trust store instead of reusing SSC's narrow one.
- Guided deployment auto-activates fcli PATH and lab TLS trust; an existing
  SSC session is reused before prompting for a token.

### Fixed

- DAST upgrade job artifact permissions.
- MySQL readiness stability during guided deployment.
- A CI-only flake in the group-activation test.
- A Flight Plans Python 3.12-only syntax bug; silent no-op upgrades are now
  guarded.
- Flight Plan discovery not surfacing the "add to local Flight Plans" step.
- Guided deployment looking frozen after the "Continue?" prompt.
- A wrong fcli flag that broke the one-click scan demo's SSC login.
- The first-scan demo's packaging step: it called `fcli sc-sast package`,
  which does not exist, and had no Maven prerequisite check.
- The first-scan demo's scan-status polling table formatting, the severity
  summary's grouping-flag casing, and a race condition where results were
  queried before SSC finished indexing the scan.
- ScanCentral SAST sensor left running after "stop", caused by a
  StatefulSet-name mismatch between the stop script and the sensor's actual
  (chart-version-dependent) name.
- Dashboard readiness now checks the ingress host, not just internal status.

## [0.1.0] - 2026-08-13

Initial release.

[Unreleased]: https://github.com/treisland/fortifylab/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/treisland/fortifylab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/treisland/fortifylab/releases/tag/v0.1.0
