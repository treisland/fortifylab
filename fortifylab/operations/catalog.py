"""Catalog of existing Bash lifecycle scripts exposed to the Python TUI."""

from __future__ import annotations

from collections.abc import Iterable

from fortifylab.paths import repo_root

from .models import CommandPlan, Operation, OperationCategory, OperationPreview


APP_SCRIPTS: tuple[dict[str, object], ...] = (
    {
        "id": "mysql",
        "label": "MySQL",
        "category": OperationCategory.COMPONENT,
        "sample": False,
        "start": ("apps/mysql/start.sh",),
        "stop": ("apps/mysql/stop.sh",),
        "destroy": ("apps/mysql/destroy.sh",),
    },
    {
        "id": "postgresql",
        "label": "PostgreSQL",
        "category": OperationCategory.COMPONENT,
        "sample": False,
        "start": ("apps/postgresql/start.sh",),
        "stop": ("apps/postgresql/stop.sh",),
        "destroy": ("apps/postgresql/destroy.sh",),
    },
    {
        "id": "ssc",
        "label": "SSC",
        "category": OperationCategory.COMPONENT,
        "sample": False,
        "start": ("apps/ssc/start.sh",),
        "stop": ("apps/ssc/stop.sh",),
        "destroy": ("apps/ssc/destroy.sh",),
    },
    {
        "id": "lim",
        "label": "LIM",
        "category": OperationCategory.COMPONENT,
        "sample": False,
        "start": ("apps/lim/start.sh",),
        "stop": ("apps/lim/stop.sh",),
        "destroy": ("apps/lim/destroy.sh",),
    },
    {
        "id": "scancentral_sast",
        "label": "ScanCentral SAST",
        "category": OperationCategory.COMPONENT,
        "sample": False,
        "start": ("apps/scsast/start.sh",),
        "stop": ("apps/scsast/stop.sh",),
        "destroy": ("apps/scsast/destroy.sh",),
    },
    {
        "id": "scancentral_dast",
        "label": "ScanCentral DAST",
        "category": OperationCategory.COMPONENT,
        "sample": False,
        "start": ("apps/scdast/core/start.sh", "apps/scdast/scanner/start.sh"),
        "stop": ("apps/scdast/core/stop.sh", "apps/scdast/scanner/stop.sh"),
        "destroy": ("apps/scdast/core/destroy.sh", "apps/scdast/scanner/destroy.sh"),
    },
    {
        "id": "juice_shop",
        "label": "Juice Shop",
        "category": OperationCategory.SAMPLE_APP,
        "sample": True,
        "start": ("apps/samples/juice-shop/start.sh",),
        "stop": ("apps/samples/juice-shop/stop.sh",),
        "destroy": ("apps/samples/juice-shop/destroy.sh",),
    },
    {
        "id": "webgoat",
        "label": "WebGoat",
        "category": OperationCategory.SAMPLE_APP,
        "sample": True,
        "start": ("apps/samples/webgoat/start.sh",),
        "stop": ("apps/samples/webgoat/stop.sh",),
        "destroy": ("apps/samples/webgoat/destroy.sh",),
    },
    {
        "id": "dvwa",
        "label": "DVWA",
        "category": OperationCategory.SAMPLE_APP,
        "sample": True,
        "start": ("apps/samples/dvwa/start.sh",),
        "stop": ("apps/samples/dvwa/stop.sh",),
        "destroy": ("apps/samples/dvwa/destroy.sh",),
    },
)


ACTION_LABELS = {
    "start": "Start / upgrade",
    "stop": "Stop",
    "destroy": "Destroy",
}


def bash_script(script_path: str, *, label: str | None = None) -> CommandPlan:
    """Create a repo-root relative Bash script command plan."""

    return CommandPlan(argv=("bash", script_path), cwd=repo_root(), label=label or script_path)


def operation_preview(operation: Operation) -> OperationPreview:
    """Return a dry-run preview without executing any commands."""

    return OperationPreview(
        operation_id=operation.id,
        label=operation.label,
        mutating=operation.mutating,
        confirmation_required=operation.confirmation_required,
        commands=tuple(command.preview() for command in operation.command_plan),
        confirmation_prompt=operation.confirmation_prompt,
    )


def get_operation(operation_id: str) -> Operation:
    """Return one catalog entry by stable id."""

    try:
        return OPERATION_CATALOG[operation_id]
    except KeyError as exc:
        raise KeyError(f"Unknown operation: {operation_id}") from exc


def list_operations(*, category: OperationCategory | None = None) -> tuple[Operation, ...]:
    """Return catalog entries in deterministic display order."""

    operations = tuple(OPERATION_CATALOG[operation_id] for operation_id in OPERATION_ORDER)
    if category is None:
        return operations
    return tuple(operation for operation in operations if operation.category == category)


def preview_operation(operation_id: str) -> OperationPreview:
    """Return the dry-run preview for a catalog operation id."""

    return operation_preview(get_operation(operation_id))


def _component_operations() -> Iterable[Operation]:
    for app in APP_SCRIPTS:
        component_id = str(app["id"])
        component_label = str(app["label"])
        category = app["category"]
        assert isinstance(category, OperationCategory)
        for action in ("start", "stop", "destroy"):
            scripts = tuple(str(script) for script in app[action])
            destructive = action == "destroy"
            yield Operation(
                id=f"{component_id}.{action}",
                label=f"{ACTION_LABELS[action]} {component_label}",
                category=category,
                command_plan=tuple(bash_script(script) for script in scripts),
                mutating=True,
                confirmation_required=True,
                description=f"Runs the existing Bash {action} script for {component_label}.",
                confirmation_prompt=_confirmation_prompt(action, component_label),
                tags=(component_id, action, "destructive" if destructive else "lifecycle"),
            )


def _lab_operation(action: str) -> Operation:
    non_sample_apps = tuple(app for app in APP_SCRIPTS if not bool(app["sample"]))
    ordered_apps = tuple(reversed(non_sample_apps)) if action in {"stop", "destroy"} else non_sample_apps
    scripts: list[str] = []
    for app in ordered_apps:
        scripts.extend(str(script) for script in app[action])

    return Operation(
        id=f"lab.{action}.all",
        label=f"{ACTION_LABELS[action]} all lab components",
        category=OperationCategory.LAB_LIFECYCLE,
        command_plan=tuple(bash_script(script) for script in scripts),
        mutating=True,
        confirmation_required=True,
        description=(
            "Runs existing Bash lifecycle scripts for core lab components "
            "in dependency-aware order."
        ),
        confirmation_prompt=_confirmation_prompt(action, "all lab components"),
        tags=("lab", action, "all", "destructive" if action == "destroy" else "lifecycle"),
    )


def _confirmation_prompt(action: str, target: str) -> str:
    if action == "destroy":
        return f"Type DESTROY to destroy {target} and its data."
    return f"Confirm before running {ACTION_LABELS[action].lower()} for {target}."


def _build_catalog() -> tuple[tuple[str, Operation], ...]:
    operations = [*_component_operations()]
    operations.extend(_lab_operation(action) for action in ("start", "stop", "destroy"))
    return tuple((operation.id, operation) for operation in operations)


_CATALOG_ITEMS = _build_catalog()
OPERATION_ORDER = tuple(operation_id for operation_id, _operation in _CATALOG_ITEMS)
OPERATION_CATALOG = dict(_CATALOG_ITEMS)
