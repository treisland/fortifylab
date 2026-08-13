# Secrets and licenses

Operational screens report only **present**, **missing**, or **unreadable** by
default. They must never casually display values for passwords,
controller/service tokens, Docker credentials, license files, TLS private keys,
database credentials, or SSC `secret.key`. The wizard's **URLs & credentials**
screen is the explicit exception for lab-generated operational credentials: it
can reveal one selected password or token after the operator types `REVEAL`, and
it can print retrieval commands. Revealed values are not written to wizard logs,
diagnostics, `.env`, or generated summary files.

Keep user-provided licenses outside Git; licensing terms still apply in a lab.
Do not put a license into a diagnostic archive. If a registry credential may
have appeared in output, revoke or rotate it through the registry and recreate
the Kubernetes Secret without echoing the replacement.

SSC `secret.key` protects stored credentials. Preserve it with the SSC database
and restore the matching pair. Replacing it after SSC stores encrypted values
can make those values unrecoverable.
