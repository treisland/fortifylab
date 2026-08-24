"""Live per-app pod status -- the read-only replacement for
``app_status()`` in ``scripts/wizard/operations.sh``.

Bash's version: list pods, filter by a prefix, count how many are
``Running`` with all containers ready (``READY`` column ``x/y`` where
``x == y``), and print "not deployed" (dim) if none matched, "N/M ready"
(yellow) if some but not all are ready, or "N/N running" (green) once
every matched pod is fully ready. This is a straight structural port of
that: same three states, same kubectl source (a single
``get pods --no-headers`` call, then filtered/parsed in Python instead of
piped through ``awk``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .kubectl_base import KubectlBackedService

__all__ = ["AppStatus", "AppStatusService"]


@dataclass(frozen=True)
class AppStatus:
    ready: int = 0
    total: int = 0

    @property
    def deployed(self) -> bool:
        return self.total > 0

    @property
    def fully_ready(self) -> bool:
        return self.deployed and self.ready == self.total


@dataclass
class AppStatusService(KubectlBackedService):
    namespace: str = "fortify"

    def status(self, pod_prefix: str) -> AppStatus:
        return self.statuses({"_": pod_prefix})["_"]

    def statuses(self, prefixes: dict[str, str]) -> dict[str, AppStatus]:
        """Like :meth:`status`, but for every app at once from a single
        ``kubectl get pods`` call -- a per-app-row refresh (the Applications
        screen has one row per app) would otherwise mean N kubectl
        round-trips for the same underlying pod list."""

        result = self._run(("-n", self.namespace, "get", "pods", "--no-headers"))
        if not result.ok:
            return {key: AppStatus() for key in prefixes}

        all_pods = [fields for line in result.stdout.splitlines() if (fields := line.split())]
        return {key: self._status_for_prefix(all_pods, prefix) for key, prefix in prefixes.items()}

    @staticmethod
    def _status_for_prefix(all_pods: list[list[str]], pod_prefix: str) -> AppStatus:
        matching = [fields for fields in all_pods if fields[0].startswith(pod_prefix)]
        total = len(matching)
        ready = 0
        for fields in matching:
            if len(fields) < 3:
                continue
            ready_column, status_column = fields[1], fields[2]
            if status_column != "Running":
                continue
            actual, desired = (ready_column.split("/") + ["", ""])[:2]
            if actual and actual == desired:
                ready += 1
        return AppStatus(ready=ready, total=total)
