"""Kubernetes Dashboard access token issuance -- the live replacement for
the ephemeral-token half of ``dashboard_access_menu()`` in
``scripts/wizard/operations.sh``.

Scope, deliberately narrow: only the two 1-hour tokens (view-only,
administrator), which Bash itself gates with nothing more than a plain
y/N confirm for admin -- exactly what this screen's existing arm-before-
execute pattern already expresses. Persistent (non-expiring) tokens are
NOT ported: Bash requires typing the literal word ``PERSISTENT`` to create
a persistent administrator token, and there is no text-entry widget in the
TUI to gate that with the same care. The auto-repair-by-redeploying-the-
Dashboard fallback in Bash's ``ensure_dashboard_access`` also isn't ported
here -- that's a deploy operation, out of scope for an access-token
screen; this service only checks whether the Dashboard's resources exist
and reports if they don't, rather than silently redeploying anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fortifylab.core.command import CommandResult, run_command

KubectlRunner = Callable[[tuple[str, ...]], CommandResult]

_VIEWER_SERVICE_ACCOUNT = "fortify-dashboard-viewer"
_ADMIN_SERVICE_ACCOUNT = "fortify-dashboard-admin"


@dataclass
class DashboardAccessService:
    kubectl: str = "microk8s kubectl"
    runner: KubectlRunner | None = None
    _namespace_cache: str | None = field(default=None, init=False, repr=False, compare=False)

    def _run(self, args: tuple[str, ...]) -> CommandResult:
        if self.runner is not None:
            return self.runner(args)
        return run_command((*tuple(self.kubectl.split()), *args), timeout=20)

    def namespace(self) -> str:
        # The Dashboard's namespace can't change during a screen's lifetime,
        # and this service is constructed once per screen -- so probing it
        # via kubectl on every call (resources_ready() and _create_token()
        # both call this on every keypress) is a redundant round-trip after
        # the first. Memoize it for the life of this service instance.
        if self._namespace_cache is None:
            result = self._run(("-n", "kubernetes-dashboard", "get", "service", "kubernetes-dashboard-kong-proxy"))
            self._namespace_cache = "kubernetes-dashboard" if result.ok else "kube-system"
        return self._namespace_cache

    def resources_ready(self) -> bool:
        namespace = self.namespace()
        service = "kubernetes-dashboard-kong-proxy" if namespace == "kubernetes-dashboard" else "kubernetes-dashboard"
        resources = (
            f"service/{service}",
            f"serviceaccount/{_VIEWER_SERVICE_ACCOUNT}",
            f"serviceaccount/{_ADMIN_SERVICE_ACCOUNT}",
            "ingress/ingress-dashboard",
        )
        return all(self._run(("-n", namespace, "get", resource)).ok for resource in resources)

    def create_viewer_token(self, *, duration: str = "1h") -> CommandResult:
        return self._create_token(_VIEWER_SERVICE_ACCOUNT, duration=duration)

    def create_admin_token(self, *, duration: str = "1h") -> CommandResult:
        return self._create_token(_ADMIN_SERVICE_ACCOUNT, duration=duration)

    def _create_token(self, service_account: str, *, duration: str) -> CommandResult:
        namespace = self.namespace()
        return self._run(("-n", namespace, "create", "token", service_account, "--duration", duration))
