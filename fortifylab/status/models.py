"""Read-only status models for Fortify Lab."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComponentStatus:
    name: str
    ready: int
    desired: int
    status: str
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.ready >= self.desired and self.status == "ready"


@dataclass(frozen=True)
class LabStatus:
    namespace: str
    cluster: str
    components: tuple[ComponentStatus, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.warnings and all(component.ok for component in self.components)

    @property
    def summary(self) -> str:
        ready = sum(1 for component in self.components if component.ok)
        return f"{ready}/{len(self.components)} components ready"


def build_check_status() -> LabStatus:
    return LabStatus(
        namespace="fortify",
        cluster="clone-safe",
        components=(
            ComponentStatus("config", 1, 1, "ready"),
            ComponentStatus("operations", 1, 1, "ready"),
        ),
    )


def render_status(status: LabStatus) -> str:
    lines = ["FortifyLab Status", f"cluster: {status.cluster}", f"namespace: {status.namespace}", f"components: {status.summary}"]
    for component in status.components:
        lines.append(f"- {component.name}: {component.ready}/{component.desired} {component.status}")
    for warning in status.warnings:
        lines.append(f"WARN: {warning}")
    return "\n".join(lines) + "\n"


def status_command(*, check: bool = False, print_line=print) -> int:
    status = build_check_status()
    for line in render_status(status).rstrip().splitlines():
        print_line(line)
    return 0 if status.ok else 1
