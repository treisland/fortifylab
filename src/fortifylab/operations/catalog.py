"""Operation catalog for existing Fortify Lab deployment actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperationKind(str, Enum):
    CERTIFICATE = "certificate"
    SECRET = "secret"
    APP_LIFECYCLE = "app-lifecycle"
    CLUSTER_LIFECYCLE = "cluster-lifecycle"
    LOGS = "logs"
    RUNBOOK = "runbook"


class OperationImpact(str, Enum):
    READ_ONLY = "read-only"
    MUTATION = "mutation"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class OperationSpec:
    operation_id: str
    label: str
    kind: OperationKind
    command: tuple[str, ...]
    impact: OperationImpact = OperationImpact.MUTATION
    warning: str = ""
    confirmation_phrase: str | None = None

    @property
    def mutates(self) -> bool:
        return self.impact is not OperationImpact.READ_ONLY


class OperationCatalog:
    """Describe current Bash-backed operations without hiding their mutating nature."""

    def __init__(self, repo_root: str = ".") -> None:
        self.repo_root = repo_root.rstrip("/")

    def list(self) -> tuple[OperationSpec, ...]:
        return (
            self.certs(),
            self.secrets(),
            self.app("ssc", "start"),
            self.app("ssc", "stop"),
            self.app("ssc", "destroy"),
            self.cluster("start"),
            self.cluster("stop"),
            self.logs("ssc-webapp-0", follow=False),
            self.runbook("first-scan"),
        )

    def get(self, operation_id: str) -> OperationSpec:
        for spec in self.list():
            if spec.operation_id == operation_id:
                return spec
        if operation_id.startswith("logs."):
            pod = operation_id.removeprefix("logs.")
            if pod and all(char.isalnum() or char in ".-" for char in pod):
                return self.logs(pod, follow=False)
        if operation_id.startswith("app."):
            parts = operation_id.split(".")
            if len(parts) == 3:
                return self.app(parts[1], parts[2])
        if operation_id.startswith("cluster."):
            parts = operation_id.split(".")
            if len(parts) == 2:
                return self.cluster(parts[1])
        raise ValueError(f"Unsupported operation: {operation_id}")

    def certs(self) -> OperationSpec:
        return OperationSpec("certs.generate", "Generate TLS certificates", OperationKind.CERTIFICATE, self._script("scripts/create-certs.sh"))

    def secrets(self) -> OperationSpec:
        return OperationSpec(
            "secrets.create",
            "Create Kubernetes Secrets",
            OperationKind.SECRET,
            self._script("scripts/create-secrets.sh"),
            warning="May rotate SSC secret.key and should be used deliberately.",
            confirmation_phrase="REFRESH SECRETS",
        )

    def app(self, app_id: str, action: str) -> OperationSpec:
        if action not in ("start", "stop", "destroy"):
            raise ValueError(f"Unsupported app operation: {action}")
        script = {
            "ssc": "apps/ssc/{action}.sh",
            "lim": "apps/lim/{action}.sh",
            "mysql": "apps/mysql/{action}.sh",
            "postgresql": "apps/postgresql/{action}.sh",
            "scsast": "apps/scsast/{action}.sh",
            "scdast-core": "apps/scdast/core/{action}.sh",
            "scdast-scanner": "apps/scdast/scanner/{action}.sh",
        }.get(app_id)
        if script is None:
            raise ValueError(f"Unsupported app operation: {app_id}")
        impact = OperationImpact.DESTRUCTIVE if action == "destroy" else OperationImpact.MUTATION
        phrase = f"DESTROY {app_id}" if impact is OperationImpact.DESTRUCTIVE else None
        return OperationSpec(
            f"app.{app_id}.{action}",
            f"{action.title()} {app_id}",
            OperationKind.APP_LIFECYCLE,
            self._script(script.format(action=action)),
            impact=impact,
            confirmation_phrase=phrase,
        )

    def cluster(self, action: str) -> OperationSpec:
        if action not in ("start", "stop"):
            raise ValueError(f"Unsupported cluster operation: {action}")
        return OperationSpec(
            f"cluster.{action}",
            f"{action.title()} MicroK8s cluster",
            OperationKind.CLUSTER_LIFECYCLE,
            ("microk8s", action),
            impact=OperationImpact.MUTATION,
            warning="Cluster lifecycle affects every Fortify Lab service but does not delete persistent data.",
        )

    def logs(self, pod: str, *, follow: bool) -> OperationSpec:
        command = ("microk8s", "kubectl", "-n", "fortify", "logs", pod)
        if follow:
            command = (*command, "-f")
        return OperationSpec(f"logs.{pod}", f"View logs for {pod}", OperationKind.LOGS, command, impact=OperationImpact.READ_ONLY)

    def lifecycle_plan(self, action: str, apps: tuple[str, ...]) -> tuple[OperationSpec, ...]:
        ordered = apps if action == "start" else tuple(reversed(apps))
        return tuple(self.app(app_id, "stop" if action == "shutdown" else action) for app_id in ordered)

    def runbook(self, topic: str) -> OperationSpec:
        allowed = {
            "first-scan": "docs/operations/first-scan.md",
            "backup": "docs/operations/backup-and-recovery.md",
            "troubleshooting": "docs/operations/troubleshooting.md",
        }
        if topic not in allowed:
            raise ValueError(f"Unsupported runbook topic: {topic}")
        path = allowed[topic]
        return OperationSpec("runbook.safe-preview", f"Preview runbook {topic}", OperationKind.RUNBOOK, ("sed", "-n", "1,160p", path), impact=OperationImpact.READ_ONLY)

    def _script(self, relative: str) -> tuple[str, ...]:
        prefix = f"{self.repo_root}/" if self.repo_root != "." else "./"
        return (f"{prefix}{relative}",)
