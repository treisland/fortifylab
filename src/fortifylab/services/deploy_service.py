"""Guided deployment use case: the live DAG-driven replacement for
``scripts/wizard/guided.sh``'s deployment loop, for the profiles the
existing :class:`~fortifylab.orchestration.adapters.BashOperationAdapter`
already knows how to run.

Scope for M3: one profile at a time, steps run one at a time in dependency
order, dry-run by default.

A real (``execute=True``) step still ultimately calls
``OperationController.run()``, a blocking subprocess call -- but
:meth:`start_execute` runs that call on a background thread so the screen
can show ``running`` immediately instead of freezing until a step that can
take several minutes returns (bug report: "no way to tell tasks are
currently running"). :meth:`poll_execute` is the other half: call it on
every tick to pick up the result once the background thread finishes.
``run_next(execute=True)`` stays as a synchronous convenience for direct/
test callers that want to block until a step actually finishes.
"""

from __future__ import annotations

import threading

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
        plan = adapter.build_plan(profile.label, step_ids)
        self._init_from_plan(plan, session_id=f"deploy-{profile_id}", controller=controller)

    @classmethod
    def for_plan(cls, plan: DeploymentPlan, *, session_id: str, controller: OperationController | None = None) -> "DeployService":
        """Build a service around an already-constructed plan instead of
        deriving one from a guided-deployment profile.

        Every piece of this class beyond plan construction -- live
        per-step state, the background-thread execute/poll mechanism, the
        dry-run preview cursor -- is exactly what a bulk lab-lifecycle
        action (start/shutdown a set of apps in order) also needs. Rather
        than a third copy of that machinery (the first was
        ``ApplicationsScreen`` before it was pointed at this same class),
        ``LabLifecycleService`` just builds a plan and hands it here; see
        ``tui.screens.lab_lifecycle``.
        """

        service = cls.__new__(cls)
        service.profile_id = ""
        service._init_from_plan(plan, session_id=session_id, controller=controller)
        return service

    def _init_from_plan(self, plan: DeploymentPlan, *, session_id: str, controller: OperationController | None) -> None:
        self.plan = plan
        self.controller = controller or OperationController()
        self.states: dict[str, OperationState] = {
            step_id: OperationState(step_id) for step_id in self.plan.step_ids()
        }
        self._preview_cursor = 0
        self._execution_lock = threading.Lock()
        self._running_thread: threading.Thread | None = None
        self._pending_result: OperationResult | None = None
        self.session = GuidedSession(
            session_id=session_id,
            profile_id=self.profile_id,
            current_step=self.plan.steps[0].step_id if self.plan.steps else "",
        )

    def runnable_steps(self) -> tuple[DeploymentStep, ...]:
        return self.plan.runnable_steps(self.states)

    def _pending_steps_in_plan_order(self) -> tuple[DeploymentStep, ...]:
        return tuple(step for step in self.plan.steps if self.states[step.step_id].status is StepStatus.PENDING)

    @property
    def is_complete(self) -> bool:
        return bool(self.plan.steps) and all(
            self.states[step.step_id].status is StepStatus.COMPLETE for step in self.plan.steps
        )

    @property
    def has_failed(self) -> bool:
        return any(state.status is StepStatus.FAILED for state in self.states.values())

    @property
    def is_executing(self) -> bool:
        with self._execution_lock:
            return self._running_thread is not None

    def _commit_result(self, result: OperationResult) -> None:
        self.states[result.step_id] = OperationState(result.step_id, result.status, result.attempts, result.detail)
        self.session = self.session.mark(result.step_id, result.status, result.detail)

    def start_execute(self) -> DeploymentStep | None:
        """Start the next runnable step for real, on a background thread.

        Marks the step ``RUNNING`` immediately (so the screen's very next
        render shows it, without waiting for the subprocess to return) and
        returns the step that was started, or ``None`` if nothing is
        runnable or a step is already executing. Call :meth:`poll_execute`
        on every tick to pick up the result once it's ready.
        """

        with self._execution_lock:
            if self._running_thread is not None:
                return None
            runnable = self.runnable_steps()
            if not runnable:
                return None
            step = runnable[0]
            self.states[step.step_id] = OperationState(step.step_id, StepStatus.RUNNING)
            thread = threading.Thread(target=self._run_in_background, args=(step,), daemon=True)
            self._running_thread = thread
        thread.start()
        return step

    def _run_in_background(self, step: DeploymentStep) -> None:
        result = self.controller.run(step, dry_run=False)
        with self._execution_lock:
            self._pending_result = result

    def poll_execute(self) -> OperationResult | None:
        """Call on every tick. Returns and commits the finished result once
        the background step from :meth:`start_execute` completes; returns
        ``None`` while it's still running or if nothing is executing."""

        with self._execution_lock:
            if self._pending_result is None:
                return None
            result = self._pending_result
            self._pending_result = None
            self._running_thread = None
        self._commit_result(result)
        return result

    def run_next(self, *, execute: bool) -> OperationResult | None:
        """Run the next runnable step for real, or preview one step of a
        dry-run walkthrough.

        Only an ``execute=True`` run commits a new step status: a dry-run
        preview must never advance the DAG, so a step that hasn't actually
        completed can't accidentally become unreachable
        (``DeploymentPlan.runnable_steps`` only ever offers ``PENDING``
        steps -- committing a non-terminal status from a preview would
        strand it).

        A dry-run still needs to feel like it's doing something, though:
        rather than re-previewing the same first pending step forever (the
        original behavior here, which read as "dry-run does nothing" --
        see the bug report), each dry-run call walks one step further
        through the still-pending steps in plan order, wrapping back to the
        start once every pending step has been shown. This is purely a
        preview cursor -- it never touches ``self.states``, so it can't
        desync from what execute mode would actually do next.
        """

        if execute:
            runnable = self.runnable_steps()
            if not runnable:
                return None
            step = runnable[0]
            result = self.controller.run(step, dry_run=False)
            self._commit_result(result)
            return result

        pending = self._pending_steps_in_plan_order()
        if not pending:
            return None
        if self._preview_cursor >= len(pending):
            self._preview_cursor = 0
        step = pending[self._preview_cursor]
        self._preview_cursor += 1
        result = self.controller.run(step, dry_run=True)
        return OperationResult(
            step_id=step.step_id,
            status=result.status,
            attempts=result.attempts,
            detail=f"Preview of '{step.label}': {result.detail}",
            command=result.command,
        )
