"""Bulk lab lifecycle actions -- shutdown/start scoped to either the
active deployment profile or every app this migration knows how to run,
the replacement for the non-destructive options (1, 2, 4, 5) of
``lab_lifecycle_menu()`` in ``scripts/wizard/operations.sh``.

Modeled as a :class:`~fortifylab.orchestration.model.DeploymentPlan`
(``DeployService.for_plan()``) rather than its own bespoke execution
machinery: a bulk lifecycle action is structurally just an ordered
sequence of app start/stop operations -- exactly the shape Guided Deploy
already drives. Reusing it means the same background-thread "running"
indicator and dry-run preview cursor for free, and one fewer place that
duplicates them (see ``tui.screens.lab_lifecycle``).

Destroy (options 3, 6, 7 in Bash) stays out, same reason as every other
destroy action in this migration: Bash requires typing an exact
confirmation phrase (``"DESTROY FORTIFY LAB"`` / ``"DESTROY SELECTED
PROFILE"``), and there is no text-entry widget in the TUI yet.
"""

from __future__ import annotations

from pathlib import Path

from ..config.store import ConfigStore
from ..operations import OperationCatalog
from ..orchestration import DeploymentPlan, DeploymentStep

__all__ = ["active_profile_id", "apps_for_scope", "build_lifecycle_plan"]

# Every app this migration's OperationCatalog/ApplicationsScreen knows how
# to run, in start order (mysql/postgresql before the apps that need
# them). Shutdown runs this reversed, matching Bash's own
# lab_shutdown_deployments()/lab_start_deployments() (start: index order,
# shutdown: reverse index order). SAST/DAST aren't in ApplicationsScreen's
# catalog yet (tracked in the roadmap), so they aren't here either.
_ALL_APPS: tuple[str, ...] = ("mysql", "postgresql", "ssc", "lim", "juice-shop", "webgoat", "dvwa")

# Applications-screen app_id -> tui.profiles step_id, so "selected
# profile" scope can be computed with the same profile-expansion logic
# Guided Deploy already uses instead of a second copy of it.
_APP_STEP_IDS: dict[str, str] = {
    "mysql": "mysql",
    "postgresql": "postgresql",
    "ssc": "ssc",
    "lim": "lim",
    "juice-shop": "sample_juice_shop",
    "webgoat": "sample_webgoat",
    "dvwa": "sample_dvwa",
}


def active_profile_id(env_file: Path) -> str:
    if not env_file.exists():
        return "full_lab"
    return ConfigStore(env_file).load().values().get("FORTIFY_DEPLOYMENT_PROFILE") or "full_lab"


def apps_for_scope(scope: str, *, env_file: Path) -> tuple[str, ...]:
    """``scope``: ``"all"`` or ``"selected"`` (the active profile)."""

    if scope == "all":
        return _ALL_APPS
    # Deferred: fortifylab.tui.profiles pulls in the tui package, which
    # (via tui.screens.guided_deploy) imports fortifylab.services --
    # importing this at module level would be a circular import (same
    # reason DeployService.__init__ defers it).
    from ..tui.profiles import build_profile, expand_components

    profile = build_profile(active_profile_id(env_file))
    step_ids = set(expand_components(profile.components))
    return tuple(app_id for app_id in _ALL_APPS if _APP_STEP_IDS[app_id] in step_ids)


def build_lifecycle_plan(
    action: str,
    scope: str,
    *,
    catalog: OperationCatalog | None = None,
    env_file: Path,
) -> DeploymentPlan:
    """``action``: ``"start"`` or ``"shutdown"``. ``scope``: ``"all"`` or
    ``"selected"``."""

    catalog = catalog or OperationCatalog()
    apps = apps_for_scope(scope, env_file=env_file)
    script_action = "stop" if action == "shutdown" else "start"
    ordered = tuple(reversed(apps)) if action == "shutdown" else apps
    steps = tuple(
        DeploymentStep(
            step_id=app_id,
            label=f"{script_action.title()} {app_id}",
            command=catalog.app(app_id, script_action).command,
        )
        for app_id in ordered
    )
    scope_label = "all apps" if scope == "all" else "selected profile"
    return DeploymentPlan(name=f"Lab lifecycle -- {action} ({scope_label})", steps=steps)
