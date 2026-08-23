"""Operation catalog for existing Fortify Lab deployment actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperationKind(str, Enum):
    CERTIFICATE = "certificate"
    SECRET = "secret"
    APP_LIFECYCLE = "app-lifecycle"
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
            self.logs("ssc-webapp-0", follow=False),
            self.runbook("first-scan"),
        )

    def certs(self) -> OperationSpec:
        return OperationSpec("certs.generate", "Generate TLS certificates", OperationKind.CERTIFICATE, self._script("scripts/create-certs.sh"))

    def secrets(self) -> OperationSpec:
        return OperationSpec(
            "secrets.create",
            "Create Kubernetes Secrets",
            OperationKind.SECRET,
            self._script("scripts/create-secrets.sh"),
            warning="May rotate SSC secret.key and should be used deliberately.",
        )

    def app(self, app_id: str, action: str) -> OperationSpec:
        script = {
            "ssc": "apps/ssc/{action}.sh",
            "lim": "apps/lim/{action}.sh",
            "mysql": "apps/mysql/{action}.sh",
            "postgresql": "apps/postgresql/{action}.sh",
            "juice-shop": "apps/samples/juice-shop/{action}.sh",
            "webgoat": "apps/samples/webgoat/{action}.sh",
            "dvwa": "apps/samples/dvwa/{action}.sh",
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
