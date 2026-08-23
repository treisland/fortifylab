"""Flight Plan use cases: what a TUI/CLI screen actually needs to ask for.

Docker Hub registry discovery (querying live tags to draft a new Flight
Plan candidate) stays in ``scripts/tools/flight-plans.py`` for now — it is
network-dependent and already works; porting it is not required for a
read-only Flight Plan screen. This module covers the two things a screen
does need: comparing the current ``.env`` against a plan, and sorting
version tags, both pure and independent of that network path.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ..domain.flight_plans import Catalog, DATABASE_KEYS, FORTIFY_KEYS, FlightPlanRecord

# The only keys this module ever needs out of a .env file: component/image
# version tags. Never widen this default -- .env also holds passwords,
# license paths, and registry tokens that must never round-trip through a
# general-purpose parse function. See security review on PR for M1/M2.
_DEFAULT_ALLOWED_KEYS = frozenset(FORTIFY_KEYS) | frozenset(DATABASE_KEYS)


def version_sort_key(tag: str) -> tuple[Any, ...]:
    """Natural sort key: numeric runs compare as numbers, not lexically
    (so ``26.10`` sorts after ``26.9``)."""

    pieces = re.split(r"([0-9]+)", tag)
    return tuple(int(piece) if piece.isdigit() else piece for piece in pieces)


def parse_env_file(path: Path, *, allowed_keys: Iterable[str] = _DEFAULT_ALLOWED_KEYS) -> dict[str, str]:
    """Read only ``allowed_keys`` out of a ``.env``-style file.

    This is intentionally not a general-purpose ``.env`` parser: a `.env`
    file also holds passwords, license paths, and registry tokens, and
    nothing here may return those. Callers that need a different set of
    keys must say so explicitly; there is no "give me everything" mode.
    """

    allowed = frozenset(allowed_keys)
    values: dict[str, str] = {}
    if not path.exists():
        return values
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key, raw = match.groups()
        if key not in allowed:
            continue
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            raw = raw[1:-1]
        values[key] = raw
    return values


@dataclass(frozen=True)
class FieldComparison:
    key: str
    expected: str
    current: str
    aligned: bool
    review_required: bool = False


@dataclass(frozen=True)
class EnvComparison:
    plan_id: str
    fields: tuple[FieldComparison, ...]

    @property
    def mismatched(self) -> tuple[FieldComparison, ...]:
        return tuple(field for field in self.fields if not field.aligned and not field.review_required)

    @property
    def drifted(self) -> bool:
        return bool(self.mismatched)


class FlightPlanService:
    """Read-only Flight Plan queries for CLI/TUI screens."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def plans(self, *, include_candidates: bool = True) -> tuple[FlightPlanRecord, ...]:
        plans = self.catalog.flight_plans.values()
        if include_candidates:
            return tuple(plans)
        return tuple(plan for plan in plans if not plan.is_candidate)

    def plan(self, plan_id: str) -> FlightPlanRecord:
        return self.catalog.plan(plan_id)

    def compare_env(self, plan_id: str, env_file: Path) -> EnvComparison:
        plan = self.catalog.plan(plan_id)
        env = parse_env_file(env_file)
        fields: list[FieldComparison] = []
        for key in FORTIFY_KEYS:
            expected = plan.components.get(key, "")
            current = env.get(key, "")
            fields.append(
                FieldComparison(
                    key=key,
                    expected=expected or "<review required>",
                    current=current or "<unset>",
                    aligned=bool(expected) and current == expected,
                    review_required=not expected,
                )
            )
        for key in DATABASE_KEYS:
            expected = self.catalog.database_defaults.get(key, "")
            current = env.get(key, "")
            fields.append(
                FieldComparison(
                    key=key,
                    expected=expected or "<unknown>",
                    current=current or "<unset>",
                    aligned=bool(expected) and current == expected,
                )
            )
        return EnvComparison(plan_id=plan_id, fields=tuple(fields))
