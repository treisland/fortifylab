# Secrets and licenses

Operational screens report only **present**, **missing**, or **unreadable**.
They must never display paths or values for passwords, controller/service
tokens, Docker credentials, license files, TLS private keys, database
credentials, or SSC `secret.key`.

Keep user-provided licenses outside Git; licensing terms still apply in a lab.
Do not put a license into a diagnostic archive. If a registry credential may
have appeared in output, revoke or rotate it through the registry and recreate
the Kubernetes Secret without echoing the replacement.

SSC `secret.key` protects stored credentials. Preserve it with the SSC database
and restore the matching pair. Replacing it after SSC stores encrypted values
can make those values unrecoverable.
