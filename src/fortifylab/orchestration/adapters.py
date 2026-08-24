"""Adapters between Python orchestration steps and existing Bash operations."""

from __future__ import annotations

from pathlib import Path

from .model import DeploymentPlan, DeploymentStep


DEFAULT_STEP_SCRIPTS: dict[str, tuple[str, ...]] = {
    "certs": ("bash", "./scripts/create-certs.sh"),
    "dashboard": ("bash", "./apps/kubernetes-dashboard/deploy.sh"),
    "secrets": ("bash", "./scripts/create-secrets.sh"),
    "mysql": ("bash", "./apps/mysql/start.sh"),
    "postgresql": ("bash", "./apps/postgresql/start.sh"),
    "ssc": ("bash", "./apps/ssc/start.sh"),
    "lim": ("bash", "./apps/lim/start.sh"),
    "sast_controller": ("bash", "./apps/scsast/start.sh"),
    "sast_sensor": ("bash", "./apps/scsast/start.sh"),
    "dast_core": ("bash", "./apps/scdast/core/start.sh"),
    "dast_scanner": ("bash", "./apps/scdast/scanner/start.sh"),
}

DEFAULT_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "dashboard": ("certs",),
    "secrets": ("certs",),
    "mysql": ("secrets",),
    "postgresql": ("secrets",),
    "ssc": ("mysql",),
    "lim": ("postgresql", "ssc"),
    "sast_controller": ("secrets",),
    "sast_sensor": ("sast_controller",),
    "dast_core": ("postgresql", "ssc", "lim"),
    "dast_scanner": ("dast_core",),
}


class BashOperationAdapter:
    """Build command metadata for existing Bash scripts without running them."""

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(repo_root)

    def command_for(self, step_id: str) -> tuple[str, ...]:
        script = DEFAULT_STEP_SCRIPTS[step_id]
        if self.repo_root == Path("."):
            return script
        return tuple(str(self.repo_root / part.removeprefix("./")) if part.startswith("./") else part for part in script)

    def build_step(self, step_id: str, label: str | None = None) -> DeploymentStep:
        return DeploymentStep(
            step_id=step_id,
            label=label or step_id.replace("_", " ").title(),
            command=self.command_for(step_id),
            dependencies=DEFAULT_DEPENDENCIES.get(step_id, ()),
        )

    def build_plan(self, name: str, step_ids: tuple[str, ...]) -> DeploymentPlan:
        return DeploymentPlan(name=name, steps=tuple(self.build_step(step_id) for step_id in step_ids))
