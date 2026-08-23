"""Guided deployment use case: the live DAG-driven replacement for
``scripts/wizard/guided.sh``'s deployment loop, for the profiles the
existing :class:`~fortifylab.orchestration.adapters.BashOperationAdapter`
already knows how to run.

Scope for M3: one profile at a time, steps run one at a time in dependency
order, dry-run by default. There is no background/async execution --
``OperationController.run()`` is a blocking subprocess call, same as every
other Bash-backed operation in this codebase (see
``fortifylab.core.command.run_command``), so "live" here means "the screen
reflects real state after each step returns," not a background poller.
Wiring true async/parallel execution is out of scope until a profile
actually needs it.
"""

from __future__ import annotations

from ..orchestration import (
    BashOperationAdapter,
    DeploymentPlan,
    DeploymentStep,
    GuidedSession,
    OperationController,
    OperationResult,
    OperationState,
    StepStatus,
)
from ..orchestration.adapters import DEFAULT_STEP_SCRIPTS


def adapter_step_ids() -> frozenset[str]:
    """Steps :class:`BashOperationAdapter` knows how to run today. A guided
    profile can reference steps this adapter doesn't cover yet (``prereqs``,
    ``inputs``, ``configure``, ...); those stay Bash-only until they get
    their own adapter entry."""

    return frozenset(DEFAULT_STEP_SCRIPTS)


class DeployService:
    """Owns one guided deployment run: the plan, live per-step state, and
    the resumable session record. A screen renders from this; it never
    touches ``subprocess`` or the adapter directly.
    """

    def __init__(
        self,
        profile_id: str = "ssc_only",
        *,
        repo_root: str = ".",
        controller: OperationController | None = None,
    ) -> None:
        # Deferred: fortifylab.tui.profiles pulls in the tui package, which
        # (via tui.screens.guided_deploy) imports this module -- importing
        # build_profile at module load time would be a circular import.
        from ..tui.profiles import build_profile

        self.profile_id = profile_id
        profile = build_profile(profile_id)
        adapter = BashOperationAdapter(repo_root)
        step_ids = tuple(step.step_id for step in profile.steps if step.step_id in adapter_step_ids())
        self.plan: DeploymentPlan = adapter.build_plan(profile.label, step_ids)
        self.controller = controller or OperationController()
        self.states: dict[str, OperationState] = {
            step_id: OperationState(step_id) for step_id in self.plan.step_ids()
        }
        self.session = GuidedSession(
            session_id=f"deploy-{profile_id}",
            profile_id=profile_id,
            current_step=self.plan.steps[0].step_id if self.plan.steps else "",
        )

    def runnable_steps(self) -> tuple[DeploymentStep, ...]:
        return self.plan.runnable_steps(self.states)

    @property
    def is_complete(self) -> bool:
        return bool(self.plan.steps) and all(
            self.states[step.step_id].status is StepStatus.COMPLETE for step in self.plan.steps
        )

    @property
    def has_failed(self) -> bool:
        return any(state.status is StepStatus.FAILED for state in self.states.values())

    def run_next(self, *, execute: bool) -> OperationResult | None:
        """Run (or dry-run preview) the next runnable step.

        Only an ``execute=True`` run commits a new step status: a dry-run
        preview must stay repeatable and must never advance the DAG, so a
        step that hasn't actually completed can't accidentally become
        unreachable (``DeploymentPlan.runnable_steps`` only ever offers
        ``PENDING`` steps -- committing a non-terminal status from a
        preview would strand it).
        """

        runnable = self.runnable_steps()
        if not runnable:
            return None
        step = runnable[0]
        result = self.controller.run(step, dry_run=not execute)
        if execute:
            self.states[step.step_id] = OperationState(step.step_id, result.status, result.attempts, result.detail)
            self.session = self.session.mark(step.step_id, result.status, result.detail)
        return result
