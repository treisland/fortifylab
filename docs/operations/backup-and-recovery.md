# Backup and recovery guidance

This lab has no production-grade backup, high availability, disaster recovery,
or restore guarantee. A filesystem/PVC snapshot alone may not be
application-consistent.

Before experimenting with upgrades, inventory persistent claims and create
database-native exports for MySQL/SSC and PostgreSQL/DAST using vendor guidance.
Back up the matching SSC `secret.key`, configuration, public certificates, and
required private trust material through a protected channel. Never place these
artifacts in Git or diagnostics.

Recovery order follows dependencies: storage → MySQL/PostgreSQL → matching SSC
database plus `secret.key` → SSC/LIM → SAST → DAST Core → scanner. Restore into
an isolated lab, verify database queries and application endpoints, then run a
test scan. Practice the restore; an untested archive is not recovery evidence.

Deleting persistent claims is irreversible through this wizard and must remain
separate from stop/uninstall. Database major-version changes may need a logical
migration; Helm rollback cannot undo them.
