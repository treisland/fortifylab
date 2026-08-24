"""Application-layer services: the use-case functions the CLI and TUI both
call. Screens and CLI commands should depend on this layer, never reach
into ``domain`` I/O or ``core.command`` directly, so the two front ends stay
in sync by construction."""

from __future__ import annotations

from .app_status_service import AppStatus, AppStatusService
from .dashboard_access_service import DashboardAccessService
from .deploy_service import DeployService, adapter_step_ids
from .flight_plan_service import EnvComparison, FlightPlanService
from .lab_lifecycle_service import active_profile_id, apps_for_scope, build_lifecycle_plan
from .logs_service import LogsService
from .urls_credentials_service import CredentialCheck, UrlsCredentialsService

__all__ = [
    "AppStatus",
    "AppStatusService",
    "CredentialCheck",
    "DashboardAccessService",
    "DeployService",
    "EnvComparison",
    "FlightPlanService",
    "LogsService",
    "UrlsCredentialsService",
    "active_profile_id",
    "adapter_step_ids",
    "apps_for_scope",
    "build_lifecycle_plan",
]
