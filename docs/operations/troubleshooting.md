# Troubleshooting by symptom

Always diagnose the first unhealthy dependency and treat downstream failures as
symptoms. Checks should be bounded and read-only. Never paste credentials,
tokens, license data, or private configuration into output.

| Symptom | Safe investigation order |
|---|---|
| Deployment failed | First failed dependency → remediation → retry same step |
| Pod Pending | PVC binding → node capacity/scheduling → image pull state |
| Pod restarting | readiness → termination reason → dependency health |
| URL unreachable | client DNS → node → ingress → application endpoint |
| TLS warning | hostname → certificate name → lab CA trust |
| Database error | StatefulSet → PVC → authenticated suppressed-output probe |
| SSC unavailable | MySQL → SSC readiness → ingress → endpoint |
| SAST unavailable | SSC → controller token presence → controller → workers |
| DAST unavailable | PostgreSQL → SSC → LIM license/pool → Core → scanner |
| Dashboard unavailable | namespace/service → ingress → client DNS/TLS |
| License rejected | readable/non-empty presence check → entitlement/support |
| Registry pull error | entitlement → pull-Secret presence → pinned image name |

Do not delete PVCs to clear Pending/restarting pods. Do not print `kubectl
describe secret`, pod environment, logs of unknown sensitivity, or decoded
Secret values. Use the deliberately minimal diagnostics bundle when sharing
status.
