"""Flight Plan catalog model.

Ports the read-side data model from ``scripts/tools/flight-plans.py`` (a
flat script, not part of the ``fortifylab`` package) into typed, importable
dataclasses so the TUI can list/inspect Flight Plans without shelling out.

This module intentionally does not port that script's Docker Hub discovery,
promotion, or curation commands — those stay Bash/script-adapted for now
(see ``services.flight_plan_service`` for the small, pure pieces that are
worth having natively). ``scripts/tools/flight-plans.py`` remains the
authoritative CLI for catalog writes; this module only reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Any

VALID_STATUSES = frozenset({"candidate", "known-good", "recommended", "legacy", "deprecated"})

FORTIFY_KEYS: tuple[str, ...] = (
    "FORTIFY_SSC_CHART_VERSION",
    "FORTIFY_SSC_IMAGE_TAG",
    "FORTIFY_SCSAST_CHART_VERSION",
    "FORTIFY_SCSAST_CTRL_IMAGE_TAG",
    "FORTIFY_SCSAST_WORKER_IMAGE_TAG",
    "FORTIFY_SCDAST_CHART_VERSION",
    "FORTIFY_LIM_CHART_VERSION",
)

DATABASE_KEYS: tuple[str, ...] = (
    "FORTIFY_MYSQL_CHART_VERSION",
    "FORTIFY_MYSQL_IMAGE_TAG",
    "FORTIFY_POSTGRES_CHART_VERSION",
    "FORTIFY_POSTGRES_IMAGE_TAG",
)


@dataclass(frozen=True)
class FlightPlanRecord:
    """A single Flight Plan entry, typed instead of a raw TOML dict."""

    plan_id: str
    label: str
    status: str
    family: str
    notes: str
    components: dict[str, str]

    @classmethod
    def from_raw(cls, plan_id: str, raw: dict[str, Any]) -> "FlightPlanRecord":
        return cls(
            plan_id=plan_id,
            label=raw.get("label", plan_id),
            status=raw.get("status", "unknown"),
            family=raw.get("family", ""),
            notes=raw.get("notes", ""),
            components=dict(raw.get("components", {})),
        )

    @property
    def is_candidate(self) -> bool:
        return self.status == "candidate"

    @property
    def review_required_keys(self) -> tuple[str, ...]:
        return tuple(key for key in FORTIFY_KEYS if not self.components.get(key))

    def shape_issues(self) -> list[str]:
        """Structural checks shared by strict validation and lenient promotion."""

        issues: list[str] = []
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", self.plan_id):
            issues.append(f"{self.plan_id}: id must be lowercase letters, numbers, dot, dash, or underscore")
        if not self.label:
            issues.append(f"{self.plan_id}: label is required")
        if self.status not in VALID_STATUSES:
            issues.append(f"{self.plan_id}: status must be one of {', '.join(sorted(VALID_STATUSES))}")
        for key in FORTIFY_KEYS:
            if key not in self.components:
                issues.append(f"{self.plan_id}: missing component key {key}")
        for key in self.components:
            if key not in FORTIFY_KEYS:
                issues.append(f"{self.plan_id}: unsupported component key {key}")
        return issues


@dataclass(frozen=True)
class Catalog:
    path: Path
    data: dict[str, Any]

    @property
    def default_flight_plan(self) -> str:
        return self.data.get("default_flight_plan", "")

    @property
    def flight_plans(self) -> dict[str, FlightPlanRecord]:
        return {
            plan_id: FlightPlanRecord.from_raw(plan_id, raw)
            for plan_id, raw in self.data.get("flight_plans", {}).items()
        }

    @property
    def database_defaults(self) -> dict[str, str]:
        return dict(self.data.get("database_defaults", {}))

    def plan(self, plan_id: str) -> FlightPlanRecord:
        try:
            return self.flight_plans[plan_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Flight Plan: {plan_id}") from exc


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_catalog_path() -> Path:
    return repo_root() / "config" / "flight-plans.toml"


def local_catalog_path(base_path: Path) -> Path:
    """Sibling, gitignored catalog a user can add their own Flight Plans to
    (e.g. config/flight-plans.toml -> config/flight-plans.local.toml)
    without touching the shared, repo-owner-curated catalog."""

    return base_path.with_name(f"{base_path.stem}.local{base_path.suffix}")


def load_catalog(path: Path) -> Catalog:
    with path.open("rb") as handle:
        return Catalog(path=path, data=tomllib.load(handle))


def load_local_catalog(base_path: Path) -> Catalog:
    local_path = local_catalog_path(base_path)
    if local_path.exists():
        return load_catalog(local_path)
    return Catalog(path=local_path, data={"schema_version": 1, "flight_plans": {}})


def merged_read_catalog(base_path: Path) -> Catalog:
    """Read-only view combining the curated catalog with the user's local
    one. Local entries take precedence on id collision. schema_version,
    default_flight_plan, and database_defaults always come from the base
    catalog -- the local catalog only ever contributes flight_plans."""

    base = load_catalog(base_path)
    local = load_local_catalog(base_path)
    if not local.data.get("flight_plans"):
        return base
    data = dict(base.data)
    plans = dict(base.data.get("flight_plans", {}))
    plans.update(local.data.get("flight_plans", {}))
    data["flight_plans"] = plans
    return Catalog(path=base.path, data=data)


def validate_catalog(catalog: Catalog) -> list[str]:
    issues: list[str] = []
    if catalog.data.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    plans = catalog.flight_plans
    if not plans:
        issues.append("at least one flight plan is required")
    recommended = 0
    for plan in plans.values():
        issues.extend(plan.shape_issues())
        if plan.status == "recommended":
            recommended += 1
    if recommended != 1:
        issues.append(f"exactly one recommended Flight Plan is required; found {recommended}")
    for key in DATABASE_KEYS:
        if key not in catalog.database_defaults:
            issues.append(f"database_defaults: missing {key}")
    return issues
