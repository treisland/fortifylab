"""Contracts for live deployment status APIs."""

from __future__ import annotations

import json
import unittest

from fortifylab.core.command import CommandResult
from fortifylab.status import EventSummary, HintSeverity, LiveState, LiveStatusPoller, PodSummary, RouteSummary, hints_for_step, render_snapshot


def result(command: tuple[str, ...], stdout: str = "{}", ok: bool = True) -> CommandResult:
    return CommandResult(args=command, returncode=0 if ok else 1, stdout=stdout, stderr="failed" if not ok else "", duration_seconds=0)


PODS = {
    "items": [
        {
            "metadata": {"name": "mysql-0"},
            "status": {"phase": "Running", "containerStatuses": [{"ready": True, "restartCount": 0}]},
        },
        {
            "metadata": {"name": "ssc-webapp-0"},
            "status": {
                "phase": "Running",
                "containerStatuses": [{"ready": False, "restartCount": 1, "state": {"waiting": {"reason": "ImagePullBackOff"}}}],
            },
        },
    ]
}
EVENTS = {
    "items": [
        {
            "type": "Warning",
            "reason": "ImagePullBackOff",
            "involvedObject": {"kind": "Pod", "name": "ssc-webapp-0"},
            "message": "Back-off pulling image for ssc-webapp-0",
        },
        {
            "type": "Warning",
            "reason": "Unhealthy",
            "involvedObject": {"kind": "Pod", "name": "mysql-0"},
            "message": "Startup probe failed",
        },
    ]
}
INGRESS = {
    "items": [
        {
            "spec": {
                "tls": [{"hosts": ["ssc.fortifydemo.local"], "secretName": "ssc-tls"}],
                "rules": [{"host": "ssc.fortifydemo.local", "http": {"paths": [{"backend": {"service": {"name": "ssc-webapp"}}}]}}],
            }
        }
    ]
}
ENDPOINTS = {"items": [{"metadata": {"name": "ssc-webapp"}, "subsets": [{"addresses": [{"ip": "10.1.1.2"}]}]}]}
HELM = [{"name": "ssc", "status": "deployed", "chart": "helm-ssc", "revision": 1}]


class LiveStatusTests(unittest.TestCase):
    def test_model_serializes_enum_values(self) -> None:
        snapshot = LiveStatusPoller(runner=self.fake_runner).snapshot()
        data = snapshot.to_dict()

        self.assertEqual(data["overall_state"], "blocked")
        self.assertIsInstance(data["steps"], list)
        self.assertIn("state", data["steps"][0])

    def test_poller_uses_read_only_json_commands(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...]) -> CommandResult:
            commands.append(command)
            return self.fake_runner(command)

        LiveStatusPoller(runner=runner).snapshot()

        joined = [" ".join(command) for command in commands]
        self.assertTrue(any("get pods -o json" in command for command in joined))
        self.assertTrue(any("get events -o json" in command for command in joined))
        self.assertFalse(any("delete" in command or "apply" in command for command in joined))

    def test_missing_cluster_tools_produce_unknown_snapshot(self) -> None:
        snapshot = LiveStatusPoller(runner=lambda command: result(command, ok=False)).snapshot()

        self.assertEqual(snapshot.overall_state, LiveState.UNKNOWN)
        self.assertTrue(snapshot.tool_warnings)

    def test_pod_states_and_hints_are_mapped_to_steps(self) -> None:
        snapshot = LiveStatusPoller(runner=self.fake_runner, profile="ssc_only").snapshot()
        by_id = {step.step_id: step for step in snapshot.steps}

        self.assertEqual(by_id["mysql"].state, LiveState.COMPLETE)
        self.assertEqual(by_id["ssc"].state, LiveState.BLOCKED)
        self.assertEqual(by_id["ssc"].hints[0].severity, HintSeverity.BLOCKED)

    def test_startup_probe_hint_is_warning(self) -> None:
        hints = hints_for_step(
            "mysql",
            (PodSummary("mysql-0", 0, 1, "Running"),),
            (EventSummary("Warning", "Unhealthy", "pod/mysql-0", "Startup probe failed"),),
        )

        self.assertEqual(hints[0].severity, HintSeverity.WARNING)

    def test_pvc_and_route_hints_have_next_inspection(self) -> None:
        hints = hints_for_step(
            "ssc",
            (PodSummary("ssc-webapp-0", 0, 1, "Pending"),),
            (EventSummary("Warning", "FailedScheduling", "pod/ssc-webapp-0", "pod has unbound immediate PersistentVolumeClaims"),),
            (RouteSummary("ssc.fortifydemo.local", True, tls_secret=None, service_name="ssc-webapp", endpoints_ready=False),),
        )

        reasons = {hint.reason for hint in hints}
        self.assertIn("pvc-unbound", reasons)
        self.assertIn("tls-missing", reasons)
        self.assertTrue(all(hint.next_inspection for hint in hints))

    def test_render_snapshot_includes_steps_and_hints(self) -> None:
        rendered = render_snapshot(LiveStatusPoller(runner=self.fake_runner, profile="ssc_only").snapshot())

        self.assertIn("Deployment status: ssc_only", rendered)
        self.assertIn("ssc", rendered)
        self.assertIn("hint:", rendered)

    def fake_runner(self, command: tuple[str, ...]) -> CommandResult:
        joined = " ".join(command)
        if "get pods" in joined:
            return result(command, json.dumps(PODS))
        if "get events" in joined:
            return result(command, json.dumps(EVENTS))
        if "get ingress" in joined:
            return result(command, json.dumps(INGRESS))
        if "get endpoints" in joined:
            return result(command, json.dumps(ENDPOINTS))
        if "helm3" in joined:
            return result(command, json.dumps(HELM))
        return result(command, "{}")


if __name__ == "__main__":
    unittest.main()
