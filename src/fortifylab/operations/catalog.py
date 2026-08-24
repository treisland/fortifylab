"""Operation catalog for existing Fortify Lab deployment actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import shlex


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
        # Bash's APP_START/APP_STOP/APP_DESTROY (scripts/wizard/app-registry.sh)
        # give ScanCentral DAST two scripts (core, then scanner), run
        # sequentially via run_app_scripts() with an abort on the first
        # failure -- every other app has exactly one.
        scripts = {
            "ssc": ("apps/ssc/{action}.sh",),
            "lim": ("apps/lim/{action}.sh",),
            "mysql": ("apps/mysql/{action}.sh",),
            "postgresql": ("apps/postgresql/{action}.sh",),
            "sast": ("apps/scsast/{action}.sh",),
            "dast": ("apps/scdast/core/{action}.sh", "apps/scdast/scanner/{action}.sh"),
            "juice-shop": ("apps/samples/juice-shop/{action}.sh",),
            "webgoat": ("apps/samples/webgoat/{action}.sh",),
            "dvwa": ("apps/samples/dvwa/{action}.sh",),
        }.get(app_id)
        if scripts is None:
            raise ValueError(f"Unsupported app operation: {app_id}")
        impact = OperationImpact.DESTRUCTIVE if action == "destroy" else OperationImpact.MUTATION
        phrase = f"DESTROY {app_id}" if impact is OperationImpact.DESTRUCTIVE else None
        return OperationSpec(
            f"app.{app_id}.{action}",
            f"{action.title()} {app_id}",
            OperationKind.APP_LIFECYCLE,
            self._scripts(tuple(script.format(action=action) for script in scripts)),
            impact=impact,
            confirmation_phrase=phrase,
        )

    def logs(self, pod: str, *, follow: bool, namespace: str = "fortify") -> OperationSpec:
        command = ("microk8s", "kubectl", "-n", namespace, "logs", pod)
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
        # Invoke via bash explicitly rather than executing the path
        # directly: these scripts are intentionally not marked executable
        # in git (the Bash wizard's own convention is to always invoke
        # them as `bash "$path"`, e.g. run_app_scripts() in
        # scripts/wizard/operations.sh). Executing one directly hits
        # PermissionError on a real clone -- the same bug already fixed
        # for orchestration.adapters.DEFAULT_STEP_SCRIPTS.
        return self._scripts((relative,))

    def _scripts(self, relatives: tuple[str, ...]) -> tuple[str, ...]:
        prefix = f"{self.repo_root}/" if self.repo_root != "." else "./"
        paths = [f"{prefix}{relative}" for relative in relatives]
        if len(paths) == 1:
            return ("bash", paths[0])
        # More than one script (DAST core + scanner): chain with && so a
        # failure in the first stops the second, matching Bash's
        # run_app_scripts() abort-on-first-failure loop, while still
        # running as a single OperationSpec/command this codebase's
        # execution model (one spec, one background thread) already
        # expects. Every path here is a fixed, repo-relative literal --
        # never user input -- so shlex.quote is just defense in depth.
        joined = " && ".join(f"bash {shlex.quote(path)}" for path in paths)
        return ("bash", "-c", joined)
