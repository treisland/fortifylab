"""Scale ScanCentral SAST/DAST worker replicas -- the replacement for
``scale_workers()`` in ``scripts/wizard/operations.sh``.

Bash's version: look up the StatefulSet backing the selected app's
workers (only SAST and DAST have one), show the current replica count,
prompt for a new one, and reject anything that isn't all-digits before
calling ``kubectl scale``. This is a structural port of the same lookup
table and the same validation -- the actual free-text prompt loop lives
in ``ApplicationsScreen`` (a ``TextField``), not here, since a service
has no I/O of its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from fortifylab.core.command import CommandResult

from .kubectl_base import KubectlBackedService

__all__ = ["STATEFULSET_BY_APP", "ScaleWorkersService"]

# Matches scale_workers()'s case statement in scripts/wizard/operations.sh
# exactly -- every other app falls through to its "Scaling not supported"
# branch.
STATEFULSET_BY_APP: dict[str, str] = {
    "sast": "scancentral-sast-worker-linux",
    "dast": "sdast-scanner-scancentral-dast-scanner",
}


@dataclass
class ScaleWorkersService(KubectlBackedService):
    namespace: str = "fortify"

    def statefulset_for(self, app_id: str) -> str | None:
        return STATEFULSET_BY_APP.get(app_id)

    def current_replicas(self, app_id: str) -> str:
        """Return the StatefulSet's current replica count as a string, or
        ``"?"`` if it's unknown -- matching Bash's own
        ``|| echo "?"`` fallback for a StatefulSet that doesn't exist yet."""

        statefulset = self.statefulset_for(app_id)
        if statefulset is None:
            return "?"
        result = self._run(
            ("-n", self.namespace, "get", "statefulset", statefulset, "-o", "jsonpath={.spec.replicas}")
        )
        if not result.ok or not result.stdout.strip():
            return "?"
        return result.stdout.strip()

    def scale(self, app_id: str, replicas: str) -> CommandResult:
        """Scale ``app_id``'s StatefulSet to ``replicas``.

        ``replicas`` must already be validated (all-digits) by the
        caller -- same division of responsibility as Bash, where the
        ``[[ "$replicas" =~ ^[0-9]+$ ]]`` check happens in the prompt
        loop before ``scale_workers()`` ever calls ``kubectl scale``.
        """

        statefulset = self.statefulset_for(app_id)
        if statefulset is None:
            raise ValueError(f"Scaling not supported for app: {app_id}")
        return self._run(("-n", self.namespace, "scale", "statefulset", statefulset, f"--replicas={replicas}"))
