"""Read-only Flight Plan catalog access for FortifyLab workflows."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_STATUSES = {"candidate", "known-good", "recommended", "legacy", "deprecated"}


class FlightPlanCatalogError(ValueError):
    """Raised when a Flight Plan catalog cannot be loaded or validated."""


@dataclass(frozen=True)
class FlightPlan:
    id: str
    label: str
    status: str
    family: str
    notes: str
    components: dict[str, str]
    repositories: dict[str, str]
    source: str = "repo"

    @property
    def recommended(self) -> bool:
        return self.status == "recommended"


@dataclass(frozen=True)
class FlightPlanCatalog:
    path: Path
    local_path: Path
    default_flight_plan: str
    database_defaults: dict[str, str]
    flight_plans: tuple[FlightPlan, ...]

    def by_id(self, plan_id: str) -> FlightPlan:
        for plan in self.flight_plans:
            if plan.id == plan_id:
                return plan
        raise KeyError(f"Unknown Flight Plan: {plan_id}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_catalog_path() -> Path:
    return repo_root() / "config" / "flight-plans.toml"


def local_catalog_path(base_path: Path) -> Path:
    return base_path.with_name(f"{base_path.stem}.local{base_path.suffix}")


def load_flight_plan_catalog(path: Path | None = None, *, include_deprecated: bool = False) -> FlightPlanCatalog:
    base_path = path or default_catalog_path()
    base_data = _read_toml(base_path)
    local_path = local_catalog_path(base_path)
    local_data = _read_toml(local_path) if local_path.exists() else {"flight_plans": {}}

    default_plan = _string_field(base_data, "default_flight_plan")
    database_defaults = _string_map(base_data.get("database_defaults", {}), "database_defaults")
    base_plans = _plan_records(base_data, source="repo")
    local_plans = _plan_records(local_data, source="local")
    merged: dict[str, FlightPlan] = {plan.id: plan for plan in base_plans}
    for plan in local_plans:
        merged[plan.id] = plan

    visible = tuple(plan for plan in merged.values() if include_deprecated or plan.status != "deprecated")
    if default_plan not in {plan.id for plan in merged.values()}:
        raise FlightPlanCatalogError(f"default_flight_plan references unknown plan: {default_plan}")
    return FlightPlanCatalog(
        path=base_path,
        local_path=local_path,
        default_flight_plan=default_plan,
        database_defaults=database_defaults,
        flight_plans=_default_first(visible, default_plan),
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise FlightPlanCatalogError(f"Flight Plan catalog not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise FlightPlanCatalogError(f"Invalid Flight Plan TOML in {path}: {exc}") from exc


def _plan_records(data: dict[str, Any], *, source: str) -> tuple[FlightPlan, ...]:
    raw_plans = data.get("flight_plans", {})
    if not isinstance(raw_plans, dict):
        raise FlightPlanCatalogError("flight_plans must be a table")
    return tuple(_flight_plan(plan_id, raw_plan, source=source) for plan_id, raw_plan in raw_plans.items())


def _flight_plan(plan_id: str, raw_plan: Any, *, source: str) -> FlightPlan:
    if not isinstance(raw_plan, dict):
        raise FlightPlanCatalogError(f"{plan_id}: Flight Plan must be a table")
    label = _string_field(raw_plan, "label", plan_id=plan_id)
    status = _string_field(raw_plan, "status", plan_id=plan_id)
    if status not in VALID_STATUSES:
        raise FlightPlanCatalogError(f"{plan_id}: status must be one of {', '.join(sorted(VALID_STATUSES))}")
    return FlightPlan(
        id=plan_id,
        label=label,
        status=status,
        family=_string_field(raw_plan, "family", plan_id=plan_id),
        notes=_string_field(raw_plan, "notes", plan_id=plan_id),
        components=_string_map(raw_plan.get("components", {}), f"{plan_id}.components"),
        repositories=_string_map(raw_plan.get("repositories", {}), f"{plan_id}.repositories"),
        source=source,
    )


def _string_field(raw: dict[str, Any], key: str, *, plan_id: str | None = None) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        prefix = f"{plan_id}: " if plan_id else ""
        raise FlightPlanCatalogError(f"{prefix}{key} must be a non-empty string")
    return value


def _string_map(raw: Any, label: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise FlightPlanCatalogError(f"{label} must be a table")
    bad = [key for key, value in raw.items() if not isinstance(key, str) or not isinstance(value, str)]
    if bad:
        raise FlightPlanCatalogError(f"{label} must contain only string keys and values")
    return dict(raw)


def _default_first(plans: tuple[FlightPlan, ...], default_plan: str) -> tuple[FlightPlan, ...]:
    return tuple(sorted(plans, key=lambda plan: (plan.id != default_plan, plan.label.casefold())))
