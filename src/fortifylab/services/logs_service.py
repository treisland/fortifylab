"""Pod log discovery and tailing: the live replacement for
``scripts/wizard/menu.sh``'s ``stream_logs``/``logs_menu`` pod-selection
flow.

The Bash flow lists pods, filters by a prefix, and only prompts the
operator to choose when more than one pod matches (``should_skip_selection``
in ``operations/logs.py`` already models that). This service is the same
shape: list pods (read-only, injectable for tests), narrow by prefix, and
hand back either a single answer or the list to choose from -- no free-text
pod name entry required, which matters because the TUI doesn't have a text
input widget yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from fortifylab.core.command import run_command
from fortifylab.operations import OperationCatalog, OperationExecution, OperationRunner, matching_pods, should_skip_selection

PodLister = Callable[[], tuple[str, ...]]


def _default_pod_lister(namespace: str, kubectl: tuple[str, ...]) -> tuple[str, ...]:
    result = run_command((*kubectl, "-n", namespace, "get", "pods", "-o", "name"), timeout=20)
    if not result.ok:
        return ()
    return tuple(line.removeprefix("pod/") for line in result.stdout.splitlines() if line.strip())


@dataclass
class LogsService:
    namespace: str = "fortify"
    kubectl: str = "microk8s kubectl"
    catalog: OperationCatalog = field(default_factory=OperationCatalog)
    runner: OperationRunner = field(default_factory=OperationRunner)
    pod_lister: PodLister | None = None

    def list_pods(self) -> tuple[str, ...]:
        if self.pod_lister is not None:
            return self.pod_lister()
        return _default_pod_lister(self.namespace, tuple(self.kubectl.split()))

    def matching_pods(self, prefix: str) -> tuple[str, ...]:
        return matching_pods(self.list_pods(), prefix)

    def matching_pods_for_scope(self, prefix: str, sibling_prefixes: Sequence[str] = ()) -> tuple[str, ...]:
        """Like ``matching_pods``, but excludes pods that belong to a more
        specific sibling scope.

        The TUI's log scopes (``tui.profiles.LOG_SCOPES``) are plain prefix
        matches, but some of them overlap: ``sast_sensor``'s prefix
        ``"scancentral-sast"`` is itself a prefix of ``sast_controller``'s
        pods (``scancentral-sast-controller-0``), and ``dast_scanner``'s
        ``"sdast"`` is a prefix of ``dast_core``'s pods
        (``sdast-core-...``). A plain ``matching_pods("scancentral-sast")``
        would therefore also return the controller's pods when the operator
        picked the sensor scope. When another known scope's prefix is
        strictly longer than, and itself starts with, `prefix`, any pod
        that also matches that longer prefix belongs to the more specific
        scope, so it's excluded here.
        """
        matches = self.matching_pods(prefix)
        more_specific = tuple(
            other for other in sibling_prefixes if other != prefix and other.startswith(prefix) and len(other) > len(prefix)
        )
        if not more_specific:
            return matches
        return tuple(pod for pod in matches if not any(pod.startswith(other) for other in more_specific))

    def should_skip_selection(self, prefix: str) -> bool:
        return should_skip_selection(self.list_pods(), prefix)

    def tail(self, pod: str, *, follow: bool = False) -> OperationExecution:
        """Fetch (or, with ``follow``, start following) one pod's logs.

        Logs are a read-only operation (`OperationImpact.READ_ONLY`), so
        `OperationRunner` never dry-run gates this regardless of an
        `execute` flag -- there is nothing destructive to arm.
        """

        return self.runner.run(self.catalog.logs(pod, follow=follow, namespace=self.namespace))
