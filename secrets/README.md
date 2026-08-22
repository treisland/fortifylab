# Secrets layout

This directory contains everything required to build the Kubernetes Secrets
that the Fortify charts consume.

```
secrets/
├── input/        # user-provided files (gitignored)        — you put files here
├── templates/    # committed templates with $VAR placeholders — rendered at deploy
└── generated/    # build artifacts (gitignored)             — wiped + rebuilt each run
```

## Workflow

1. Set `FORTIFY_LICENSE_FILE` to a protected external file, or use the
   backward-compatible `input/fortify.license` default (see `input/README.md`).
2. Configure `.env` (domain, passwords, image versions).
3. Run `scripts/create-certs.sh` to generate the mkcert root + leaf cert, or
   validate and normalize BYO TLS inputs when `FORTIFY_TLS_MODE=byo`, and build
   the JVM keystore + truststore into `generated/`.
4. Run `scripts/create-secrets.sh` to render templates, generate ephemeral
   secrets (SSC `secret.key`, scancentral tokens, JWT keys), and create the
   Kubernetes Secret objects.

## Map: file → k8s Secret → consumer

The k8s Secret name and key are what the helm chart reads.

| File path                                      | k8s Secret                       | Key                  | Consumer                            |
|------------------------------------------------|----------------------------------|----------------------|-------------------------------------|
| `$FORTIFY_LICENSE_FILE` (external or default)  | `fortify-secrets`                | `fortify.license`    | SSC, ScanCentral SAST controller    |
| `templates/ssc.autoconfig.template` (rendered) | `fortify-secrets`                | `ssc.autoconfig`     | SSC (DB connection)                 |
| `generated/ssc/secret.key`                     | `fortify-secrets`                | `secret.key`         | SSC (credential encryption)         |
| `generated/certs/keystore.jks`                 | `fortify-secrets`                | `keystore.jks`       | SSC (HTTPS keystore)                |
| `generated/certs/truststore`                   | `fortify-secrets`                | `truststore`         | SSC (JVM truststore for outbound)   |
| `generated/certs/tls.crt` + `tls.key`          | `tls`                            | (TLS type)           | nginx ingress (server cert)         |
| `generated/certs/rootCA.pfx`                   | `tls-pfx`                        | `tls.pfx`            | LIM (signing/server-compatible PFX) |
| —                                              | `tls-pfx-password`               | `password`           | LIM (PFX password)                  |
| —                                              | `lim-server-certificate`         | (TLS type)           | LIM (server cert)                   |
| —                                              | `lim-admin-credentials`          | basic-auth           | LIM admin                           |
| —                                              | `lim-pool`                       | basic-auth           | LIM default pool                    |
| —                                              | `lim-jwt-security-key`           | `token`              | LIM JWT signing                     |
| —                                              | `scdast-db-owner`                | basic-auth           | SCDAST upgradejob (DBO)             |
| —                                              | `scdast-db-standard`             | basic-auth           | SCDAST API (runtime DB user)        |
| —                                              | `scdast-ssc-serviceaccount`      | basic-auth           | SCDAST → SSC                        |
| —                                              | `scdast-service-token`           | `service-token`      | SCDAST core ↔ scanner               |
| —                                              | `regcred`                        | dockerconfigjson     | image pull from Docker Hub          |

Files in `input/` and `generated/` that aren't in the table are **not**
loaded into any k8s Secret (no more "everything in the folder becomes a key"
behavior — keys are added explicitly).

### Existing-Secret contract

The prepared consumer contract is the `fortify-secrets` Kubernetes Secret in
`$NAMESPACE`, with the license stored under the exact `fortify.license` key.
SSC and ScanCentral SAST use that name and key. `create-secrets.sh` currently
materializes the Secret from `FORTIFY_LICENSE_FILE`; operators must not place
the license in Helm values or command-line literals.

Adopting a Secret that is managed outside Fortify Lab Manager is not yet an
implemented source mode. Until that lifecycle is added, do not pre-create or
manually replace `fortify-secrets`: the script rebuilds it together with other
required keys. This explicit limitation prevents silently claiming ownership
or rollback behavior that does not exist.

## Public CAs

Public certificate authorities (Amazon Root CA 1, the `update.fortify.com`
chain, etc.) are **not** stored here as secrets. They are imported into the
JVM truststore by `scripts/create-certs.sh` and travel with the
`truststore` file above. In BYO TLS mode, keep `FORTIFY_BYO_TLS_KEY` outside
Git or under the gitignored `secrets/input/` handoff area; never paste private
key material into terminal output, docs, issues, or diagnostics.
