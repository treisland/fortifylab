"""Application-layer services: the use-case functions the CLI and TUI both
call. Screens and CLI commands should depend on this layer, never reach
into ``domain`` I/O or ``core.command`` directly, so the two front ends stay
in sync by construction."""

from __future__ import annotations

from .flight_plan_service import EnvComparison, FlightPlanService

__all__ = ["EnvComparison", "FlightPlanService"]
