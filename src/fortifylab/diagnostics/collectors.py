"""Structured Kubernetes and Helm diagnostics collectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fortifylab.core.command import CommandResult, run_command


Runner = Callable[[tuple[str, ...]], CommandResult]


@dataclass(frozen=True)
class CollectorResult:
    name: str
    command: tuple[str, ...]
    ok: bool
    output: str


class ClusterCollector:
    """Collect read-only cluster and Helm snapshots through an injectable runner."""

    def __init__(self, *, namespace: str = "fortify", kubectl: str = "microk8s kubectl", helm: str = "microk8s helm3", runner: Runner | None = None) -> None:
        self.namespace = namespace
        self.kubectl = tuple(kubectl.split())
        self.helm = tuple(helm.split())
        self.runner = runner or self._default_runner

    def collect(self) -> tuple[CollectorResult, ...]:
        commands = (
            ("nodes", (*self.kubectl, "get", "nodes", "-o", "wide")),
            ("pods", (*self.kubectl, "-n", self.namespace, "get", "pods", "-o", "wide")),
            ("services", (*self.kubectl, "-n", self.namespace, "get", "services")),
            ("endpoints", (*self.kubectl, "-n", self.namespace, "get", "endpoints")),
            ("pvc", (*self.kubectl, "-n", self.namespace, "get", "pvc")),
            ("ingress", (*self.kubectl, "-n", self.namespace, "get", "ingress")),
            ("events", (*self.kubectl, "-n", self.namespace, "get", "events", "--sort-by=.lastTimestamp")),
            ("helm", (*self.helm, "-n", self.namespace, "list")),
        )
        return tuple(self._collect_one(name, command) for name, command in commands)

    def _collect_one(self, name: str, command: tuple[str, ...]) -> CollectorResult:
        result = self.runner(command)
        output = result.stdout if result.ok else result.stderr or result.stdout
        return CollectorResult(name=name, command=command, ok=result.ok, output=output)

    @staticmethod
    def _default_runner(command: tuple[str, ...]) -> CommandResult:
        return run_command(command, timeout_seconds=20)
