"""Credential *availability* checks -- the read-only half of ``urls_creds()``
in ``scripts/wizard/operations.sh``.

This service only ever answers "does this Kubernetes Secret key have a
value" (via ``secret_key_exists`` in ``scripts/wizard/guided.sh``'s own
shape: fetch the key, check it's non-empty, never decode or return it).
It never fetches, decodes, or returns an actual credential value -- that
stays Bash-wizard-only (``credential_reveal_once``, which requires typing
the literal word ``REVEAL`` first, the same typed-confirmation blocker as
destroy; there is no text-entry widget in the TUI to gate that safely).
"""

from __future__ import annotations

from dataclasses import dataclass

from .kubectl_base import KubectlBackedService, KubectlRunner

__all__ = ["CREDENTIAL_CHECKS", "CredentialCheck", "KubectlRunner", "UrlsCredentialsService"]


@dataclass(frozen=True)
class CredentialCheck:
    label: str
    secret: str
    key: str


CREDENTIAL_CHECKS: tuple[CredentialCheck, ...] = (
    CredentialCheck("LIM admin password", "lim-admin-credentials", "password"),
    CredentialCheck("LIM pool password", "lim-pool", "password"),
    CredentialCheck("SAST client auth token", "fortify-secrets", "scancentral-client-auth-token"),
    CredentialCheck("SAST worker auth token", "fortify-secrets", "scancentral-worker-auth-token"),
    CredentialCheck("SAST SSC ControllerToken", "fortify-secrets", "scancentral-ssc-scancentral-ctrl-secret"),
    CredentialCheck("DAST service token", "scdast-service-token", "service-token"),
    CredentialCheck("DAST SSC service account password", "scdast-ssc-serviceaccount", "password"),
)


@dataclass
class UrlsCredentialsService(KubectlBackedService):
    namespace: str = "fortify"

    def secret_key_exists(self, secret: str, key: str) -> bool:
        result = self._run(("-n", self.namespace, "get", "secret", secret, "-o", f"jsonpath={{.data.{key}}}"))
        return result.ok and bool(result.stdout.strip())

    def check_availability(self) -> tuple[tuple[CredentialCheck, bool], ...]:
        return tuple((check, self.secret_key_exists(check.secret, check.key)) for check in CREDENTIAL_CHECKS)
