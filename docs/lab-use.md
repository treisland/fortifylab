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

On first launch, and therefore before the first deployment, the wizard displays
the full notice and requires the operator to type `LAB`. A versioned marker is
stored in `${XDG_CONFIG_HOME}/fortify-lab/acknowledged-lab-use`, or in
`${HOME}/.config/fortify-lab/acknowledged-lab-use` when `XDG_CONFIG_HOME` is
unset. The marker contains no secret or environment configuration. It is never
stored in `.env` or elsewhere in the repository.

The main menu continues to identify the environment as lab/demo only. The
wizard repeats focused warnings before generating an administrator token and
before destructive actions. Help should expose a reset action; after reset, the
full acknowledgement is required at the next launch.

For deliberate unattended lab automation, pass `--accept-lab-use`:

```bash
./start_wizard.sh --accept-lab-use
```

This explicit flag records the same marker. It must not be inferred from a
generic `--yes`, an environment variable, redirected input, or the presence of
`.env`. Unknown arguments must still be rejected by the wizard. The flag only
acknowledges the lab-use boundary; it does not waive other confirmations,
including destructive-action confirmation.
