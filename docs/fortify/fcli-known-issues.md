# fcli and SSC known issues

## Purpose and users

Fortify Lab automates fcli and SSC through the wizard's first-scan demo and
lifecycle scripts. Building that automation surfaced several fcli/SSC
behaviors that are easy to get wrong and are not obvious from the tools'
own error messages. This page collects them for anyone extending the
wizard scripts or writing new runbooks against fcli.

## Known issues

!!! note "`fcli sc-sast package` does not exist"
    ScanCentral SAST packaging is not a `sc-sast` subcommand. It is the
    built-in SSC action `package`, run through
    `fcli ssc action run package`. Confirmed against the fcli source for
    both the `dev` branch and the `v3.23.3` tag. See
    `scan_type_package_sast_iwa_java()` in `scripts/wizard/scan-demo.sh`.

!!! note "`package` action client-version auto-detect can throw right after `setup-appversion`"
    The `package` action tries to auto-detect the ScanCentral Client
    version from an active sensor in the target application version's
    sensor pool. Immediately after creating a fresh application version,
    no sensor has picked up work yet, so auto-detect can throw instead of
    failing gracefully. Pin the version explicitly with
    `--sc-client-version` (Fortify Lab uses
    `FORTIFY_SCSAST_WORKER_IMAGE_TAG`) to avoid depending on sensor timing.

!!! note "`sc-sast scan start --publish-to` does not create the application version"
    fcli resolves the target application version with
    `getRequiredAppVersion`, which throws if the version does not already
    exist — it does not create one. Run the idempotent
    `fcli ssc action run setup-appversion --skip-if-exists` first. See
    `scan_type_setup_appversion_sast_iwa_java()` in
    `scripts/wizard/scan-demo.sh`.

!!! note "The scan job token field is `jobToken`, not `scanId`"
    `SCSastScanJobDescriptor` (the record returned by `sc-sast scan
    start`/`sc-sast scan status`) exposes the job identifier as
    `jobToken`. Referencing `::first_scan_job::scanId` from fcli's
    variable store resolves to null and breaks any command chained on it.

!!! note "`scanState`/`publishState` reaching COMPLETED does not mean SSC has finished processing"
    `SCSastScanJobDescriptor` also carries a separate `sscArtifactState`
    field, which must reach the terminal value `PROCESS_COMPLETE` (fcli's
    `SCSastScanJobArtifactState` enum has several non-terminal and failure
    states besides that one). Querying issue counts or severity summaries
    before `sscArtifactState` is terminal returns incomplete or collapsed
    results even though the scan and publish both look "done". Poll all
    three fields — see `scan_type_poll_sast_iwa_java()` in
    `scripts/wizard/scan-demo.sh`.

!!! note "`ssc issue count --by` is case-sensitive against SSC's own grouping list"
    fcli validates `--by` against a grouping list fetched dynamically from
    SSC (`SSCIssueGroupHelper`), and the match is case-sensitive. fcli's
    own default grouping is `FOLDER` (uppercase); passing a
    lowercase `folder` fails even against a successful scan with results.
    When in doubt, omit `--by` and let fcli use its default rather than
    guessing the casing.

!!! note "The ScanCentral SAST sensor StatefulSet name is not fixed"
    The sensor's StatefulSet name varies across Helm chart versions and
    configurations. A lifecycle script that hardcodes one name can
    silently no-op — the sensor keeps running after a "stop" because the
    scale command targeted a StatefulSet that does not exist. Fortify Lab
    centralizes the known names in
    `fortify_sast_sensor_statefulset_names()` in
    `scripts/lib/k8s-scale.sh` and has every stop/scale caller (including
    `apps/scsast/stop.sh`) go through that single source of truth instead
    of keeping its own copy of the name list.

!!! note "IWA-Java scanning needs Maven, not fcli"
    ScanCentral Client uses Maven's build-tool integration to resolve
    dependencies when packaging an IWA (integrated with application)
    Java build — Maven is a scan-time prerequisite for the target
    project's build, not a dependency of fcli itself. Fail closed on a
    missing `mvn` before attempting to package, rather than letting the
    package step fail with a less obvious error. See
    `scan_type_prereqs_sast_iwa_java()` in `scripts/wizard/scan-demo.sh`
    and `install_maven()`/`maven_ready()` in
    `scripts/wizard/operations.sh`.

Next: [ScanCentral SAST](scancentral-sast.md) · [SSC](ssc.md)
