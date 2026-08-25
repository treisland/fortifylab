"""Default M6 runbook and help catalog contracts."""

from __future__ import annotations

from pathlib import Path
import re

from fortifylab.paths import repo_root

from .models import (
    HelpTopic,
    RequirementResult,
    RunbookMetadata,
    RunbookParameter,
    RunbookRisk,
    RunbookValidationReport,
    check_requirements,
    source_for_path,
    source_rank,
)


HELP_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic("overview", "System overview", Path("docs/help/overview.txt"), "index.html"),
    HelpTopic("architecture", "Dependencies and data flow", Path("docs/help/architecture.txt"), "fortify/architecture-and-flows/"),
    HelpTopic("ssc", "Software Security Center (SSC)", Path("docs/help/ssc.txt"), "fortify/ssc/"),
    HelpTopic("sast", "ScanCentral SAST", Path("docs/help/sast.txt"), "fortify/scancentral-sast/"),
    HelpTopic("dast", "ScanCentral DAST", Path("docs/help/dast.txt"), "fortify/scancentral-dast/"),
    HelpTopic("lim", "License and Infrastructure Manager (LIM)", Path("docs/help/lim.txt"), "fortify/lim/"),
    HelpTopic("mysql", "MySQL", Path("docs/help/mysql.txt"), "fortify/mysql/"),
    HelpTopic("postgresql", "PostgreSQL", Path("docs/help/postgresql.txt"), "fortify/postgresql/"),
    HelpTopic("dashboard", "Kubernetes Dashboard", Path("docs/help/dashboard.txt"), "fortify/kubernetes-dashboard/"),
    HelpTopic("roles", "Roles and learning paths", Path("docs/help/roles.txt"), "fortify/"),
    HelpTopic("glossary", "Glossary", Path("docs/help/glossary.txt"), "fortify/"),
    HelpTopic("urls", "URLs and interfaces", Path("docs/help/urls.txt"), "operations/networking-and-tls/"),
    HelpTopic("lab-scope", "Lab deployment vs Fortify products", Path("docs/help/lab-scope.txt"), "safety/"),
)

HELP_ALIASES: dict[str, str] = {
    "guided/prerequisites": "overview",
    "guided/inputs": "overview",
    "guided/preflight": "overview",
    "guided/tls": "urls",
    "guided/dashboard": "dashboard",
    "guided/secrets": "overview",
    "guided/mysql": "mysql",
    "guided/postgresql": "postgresql",
    "guided/ssc": "ssc",
    "guided/lim": "lim",
    "guided/sast": "sast",
    "guided/dast": "dast",
    "guided/configuration": "urls",
    "troubleshooting/deployment": "overview",
    "troubleshooting/pending-pods": "architecture",
    "troubleshooting/restarting-pods": "architecture",
    "troubleshooting/url": "urls",
    "troubleshooting/tls": "urls",
    "troubleshooting/database": "architecture",
    "troubleshooting/ssc": "ssc",
    "troubleshooting/sast": "sast",
    "troubleshooting/dast": "dast",
    "troubleshooting/dashboard": "dashboard",
    "troubleshooting/license": "lab-scope",
    "troubleshooting/registry": "architecture",
}


def list_help_topics() -> tuple[HelpTopic, ...]:
    return HELP_TOPICS


def get_help_topic(topic_id: str) -> HelpTopic:
    target_id = HELP_ALIASES.get(topic_id, topic_id)
    for topic in HELP_TOPICS:
        if topic.id == target_id:
            if topic.id == topic_id:
                return topic
            return HelpTopic(topic_id, topic.label, topic.offline_path, topic.online_route)
    raise KeyError(f"Unknown help topic: {topic_id}")


def load_runbook(path: Path, *, runbook_root: Path | None = None) -> RunbookMetadata:
    metadata = parse_runbook_metadata(path, runbook_root=runbook_root)
    if metadata is None:
        raise ValueError(f"Not a FortifyLab runbook: {path}")
    return metadata


def validate_runbook(
    path: Path,
    *,
    runbook_root: Path | None = None,
    requirement_checker=None,
) -> RunbookValidationReport:
    errors: list[str] = []
    metadata: RunbookMetadata | None = None

    try:
        metadata = parse_runbook_metadata(path, runbook_root=runbook_root)
    except KeyError as exc:
        errors.append(f"missing required metadata field: {exc.args[0]}")
    except ValueError as exc:
        errors.append(str(exc))

    if metadata is None:
        fields = _raw_metadata_fields(path)
        if fields.get("fortifylab-runbook") != "true":
            errors.append("missing fortifylab-runbook marker")
        for field in ("name", "description"):
            if not fields.get(field):
                errors.append(f"missing required metadata field: {field}")
        risk = fields.get("risk")
        if risk:
            try:
                RunbookRisk(risk)
            except ValueError:
                errors.append(f"invalid risk: {risk}")

    requires = metadata.requires if metadata is not None else tuple(_split_requires(_raw_metadata_fields(path).get("requires", "")))
    checker = requirement_checker or (lambda tools: check_requirements(tools))
    requirement_results = tuple(checker(requires)) if requires else ()
    for result in requirement_results:
        available = getattr(result, "available", None)
        tool = getattr(result, "tool", getattr(result, "name", "requirement"))
        detail = getattr(result, "detail", "missing")
        if isinstance(result, RequirementResult):
            available = result.available
        if available is False:
            errors.append(f"missing requirement {tool}: {detail}")

    return RunbookValidationReport(metadata=metadata, errors=tuple(errors), requirement_results=requirement_results)


def discover_runbooks(root: Path | None = None) -> tuple[RunbookMetadata, ...]:
    runbook_root = root or repo_root() / "runbooks"
    records = []
    for folder in ("official", "training", "local"):
        directory = runbook_root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.sh")):
            metadata = parse_runbook_metadata(path, runbook_root=runbook_root)
            if metadata is not None:
                records.append(metadata)
    return tuple(
        sorted(
            records,
            key=lambda item: (item.domain.lower(), source_rank(item.source), item.category.lower(), item.order, item.name.lower(), str(item.path)),
        )
    )


def parse_runbook_metadata(path: Path, *, runbook_root: Path | None = None) -> RunbookMetadata | None:
    fields: dict[str, str] = {
        "category": "General",
        "domain": "General",
        "order": "1000",
        "type": "script",
    }
    parameters: list[dict[str, str]] = []
    current_param: dict[str, str] | None = None
    marker = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("#"):
            continue
        comment = stripped[1:].strip()
        if not comment:
            continue
        if comment.startswith("- name:"):
            current_param = {"name": _trim_value(comment.split(":", 1)[1])}
            parameters.append(current_param)
            continue
        if current_param is not None:
            param_match = re.match(r"^(description|default|defaultFromEnv|required):\s*(.*)$", comment)
            if param_match:
                current_param[param_match.group(1)] = _trim_value(param_match.group(2))
                continue
        field_match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", comment)
        if field_match:
            key = field_match.group(1)
            value = _trim_value(field_match.group(2))
            if key == "fortifylab-runbook" and value == "true":
                marker = True
            else:
                fields[key] = value

    if not marker:
        return None
    risk = RunbookRisk(fields.get("risk", "low"))
    base = runbook_root or repo_root() / "runbooks"
    runbook_id = str(path.relative_to(base).with_suffix("")) if path.is_relative_to(base) else path.stem
    return RunbookMetadata(
        id=runbook_id.replace("/", "."),
        name=fields["name"],
        description=fields["description"],
        path=path,
        source=source_for_path(path, base),
        domain=fields.get("domain", "General"),
        category=fields.get("category", "General"),
        risk=risk,
        order=int(fields.get("order", "1000")),
        requires=tuple(_split_requires(fields.get("requires", ""))),
        type=fields.get("type", "script"),
        parameters=tuple(_build_parameter(data) for data in parameters),
    )


def _build_parameter(data: dict[str, str]) -> RunbookParameter:
    return RunbookParameter(
        name=data["name"],
        description=data.get("description", ""),
        default=data.get("default", ""),
        default_from_env=data.get("defaultFromEnv", ""),
        required=data.get("required", "false").lower() in {"true", "yes", "1"},
    )


def _split_requires(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[,\s]+", value) if part)


def _trim_value(value: str) -> str:
    return value.strip().strip("\"'")


def _raw_metadata_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("#"):
            continue
        comment = stripped[1:].strip()
        field_match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$", comment)
        if field_match:
            fields[field_match.group(1)] = _trim_value(field_match.group(2))
    return fields
