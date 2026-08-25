# Lab and demo use boundary

This repository's deployment architecture and automation are intended only for
evaluation, demonstrations, training, and isolated lab use. They are not a
production deployment architecture and do not provide production-grade high
availability, security hardening, backup, disaster recovery, monitoring, or
support guarantees.

This boundary applies to the architecture and automation in this repository;
it does **not** limit the production capabilities of Fortify products.

Do not use this lab for production workloads, regulated or business-critical
data, real credentials, customer data, production source code, or production
scan results. Restrict network exposure, replace example credentials, and
follow applicable Fortify licensing terms. There is no option that converts
this lab automation into a production-ready installation.

## Acknowledgement

On first guided launch, and therefore before the first deployment, Fortify Lab
displays the full notice and requires the operator to type `LAB`. A versioned marker is
stored in `${XDG_CONFIG_HOME}/fortify-lab/acknowledged-lab-use`, or in
`${HOME}/.config/fortify-lab/acknowledged-lab-use` when `XDG_CONFIG_HOME` is
unset. The marker contains no secret or environment configuration. It is never
stored in `.env` or elsewhere in the repository.

The guided interface continues to identify the environment as lab/demo only.
Fortify Lab repeats focused warnings before generating an administrator token
and before destructive actions. Help should expose a reset action; after reset,
the full acknowledgement is required at the next guided launch.

The retired Bash wizard `--accept-lab-use` flag is not part of the supported M7
compatibility shim. Unattended acknowledgement should be restored only through
a deliberate Python CLI/TUI command with tests that preserve the same safety
boundary: it must not be inferred from a generic `--yes`, an environment
variable, redirected input, or the presence of `.env`, and it must not waive
other confirmations, including destructive-action confirmation.
