# ScanCentral SAST

## Purpose and users

ScanCentral SAST distributes static analysis so approved source or build inputs
can be processed by controller and worker services. Developers submit training
jobs; security analysts consume the resulting findings in SSC; lab operators
maintain controller connectivity and worker capacity.

## Data and interfaces

- **Data:** clients submit job inputs and workers produce analysis output. Do
  not submit production source, credentials, or other sensitive material to
  this demo environment.
- **UI/API:** use an approved ScanCentral client or integration for job
  submission and SSC for applications, versions, and findings. Exact client and
  API behavior is version-specific.
- **Scan role:** the controller schedules work and Linux workers perform static
  analysis. Results flow into the SSC-centered application-security workflow;
  SSC remains the system of record.

## Dependencies

The SAST controller can run independently when the lab is using the
**SAST controller only** profile. A SAST sensor requires the controller. The
**SAST full with SSC** profile adds MySQL and SSC so results can participate in
the SSC-centered workflow. In that integrated path, the controller must receive
an SSC-created `ScanCentralCtrlToken` through the protected wizard workflow.
Storage, cluster networking, certificate trust, and the Fortify license input
must also be valid.

## Failure symptoms

Common symptoms are rejected submissions, controller authentication failures,
queued work with no available worker, workers that do not register, or results
that do not reach the intended SSC application version. For standalone
controller deployments, check controller readiness and DNS/TLS first. For the
integrated SAST full profile, also check MySQL, SSC health, controller credential
configuration, and worker readiness. Adding workers does not repair a broken
dependency.

## Stop impact

Stopping workers removes analysis capacity and may delay or interrupt active
jobs. Stopping the controller blocks scheduling and submission coordination.
It does not intentionally erase SSC findings. Confirm job state before a stop
or restart; scaling and destruction have different effects.

Next: [SSC](ssc.md) · [MySQL](mysql.md)
