"""Shared kubectl-invocation base for services that shell out to kubectl.

Every kubectl-backed service in this migration (``DashboardAccessService``,
``UrlsCredentialsService``, ``LabStatusService``, and now
``AppStatusService``) needed the exact same three things: a configurable
kubectl binary, an injectable runner for tests, and a helper that uses the
runner if given or falls back to a real ``run_command`` call with a 20s
timeout. That was copy-pasted verbatim across every one of them (flagged
in the M11/M12 code reviews as duplication worth collapsing); this is the
one place it lives now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fortifylab.core.command import CommandResult, run_command

KubectlRunner = Callable[[tuple[str, ...]], CommandResult]


@dataclass
class KubectlBackedService:
    kubectl: str = "microk8s kubectl"
    runner: KubectlRunner | None = None

    def _run(self, args: tuple[str, ...]) -> CommandResult:
        if self.runner is not None:
            return self.runner(args)
        return run_command((*tuple(self.kubectl.split()), *args), timeout=20)
