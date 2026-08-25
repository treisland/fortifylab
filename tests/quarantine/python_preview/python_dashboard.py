"""Contracts for the Phase 3.10 read-only dashboard preview."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult
from fortifylab.dashboard import DashboardCollector, collect_dashboard, render_dashboard
from fortifylab.tui import TerminalStyle


class PythonDashboardTests(unittest.TestCase):
    def test_demo_dashboard_is_deterministic_and_renders_operator_summary(self) -> None:
        rendered = render_dashboard(collect_dashboard(demo=True), style=TerminalStyle(color=False, symbols=False))

        self.assertIn("Fortify Lab Dashboard", rendered)
        self.assertIn("Source:   demo", rendered)
        self.assertIn("Software Security Center", rendered)
        self.assertIn("ScanCentral SAST", rendered)
        self.assertIn("Warnings", rendered)

    def test_collector_uses_read_only_kubectl_json_commands(self) -> None:
        commands: list[tuple[str, ...]] = []

        def fake_runner(command: tuple[str, ...]) -> CommandResult:
            commands.append(command)
            return CommandResult(command, 0, _json_for(command), "", 0.01)

        snapshot = DashboardCollector(namespace="fortify", runner=fake_runner, profile="full_lab").collect()

        self.assertEqual(snapshot.overall, "warning")
        self.assertEqual(snapshot.profile, "full_lab")
        self.assertEqual(snapshot.source, "live")
        self.assertEqual(snapshot.summary.pods, 2)
        self.assertEqual(snapshot.summary.ready_pods, 1)
        self.assertEqual(snapshot.summary.pvcs, 1)
        self.assertEqual(snapshot.summary.ingresses, 1)
        self.assertEqual(snapshot.summary.nodes_ready, 1)
        self.assertGreaterEqual(snapshot.summary.warnings, 1)
        self.assertEqual(snapshot.applications[0].name, "Software Security Center")
        self.assertEqual(snapshot.applications[0].ready, "1/1")
        self.assertIn(("microk8s", "kubectl", "get", "nodes", "-o", "json"), commands)
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "pods", "-o", "json"), commands)
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "pvc", "-o", "json"), commands)
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "ingress", "-o", "json"), commands)
        self.assertIn(("microk8s", "kubectl", "-n", "fortify", "get", "events", "-o", "json"), commands)

    def test_collector_falls_back_when_cluster_is_unavailable(self) -> None:
        def fake_runner(command: tuple[str, ...]) -> CommandResult:
            return CommandResult(command, 1, "", "microk8s is not running", 0.01)

        snapshot = DashboardCollector(runner=fake_runner).collect()
        rendered = render_dashboard(snapshot, style=TerminalStyle(color=False, symbols=False))

        self.assertEqual(snapshot.overall, "unavailable")
        self.assertEqual(snapshot.source, "unavailable")
        self.assertIn("microk8s is not running", rendered)
        self.assertIn("Warnings", rendered)


def _json_for(command: tuple[str, ...]) -> str:
    resource = command[-3]
    payloads = {
        "nodes": {
            "items": [
                {
                    "metadata": {"name": "fortifylab"},
                    "status": {
                        "capacity": {"cpu": "4", "memory": "20384920Ki"},
                        "conditions": [{"type": "Ready", "status": "True"}],
                    },
                }
            ]
        },
        "pods": {
            "items": [
                {
                    "metadata": {"name": "ssc-webapp-0"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                    },
                },
                {
                    "metadata": {"name": "mysql-0"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"ready": False, "restartCount": 1}],
                    },
                },
            ]
        },
        "pvc": {
            "items": [
                {
                    "metadata": {"name": "ssc-pvc"},
                    "spec": {"storageClassName": "nfs"},
                    "status": {"phase": "Bound", "capacity": {"storage": "20Gi"}},
                }
            ]
        },
        "ingress": {
            "items": [
                {
                    "metadata": {"name": "ssc-ingress"},
                    "spec": {"rules": [{"host": "ssc.fortifydemo.proxmox"}]},
                }
            ]
        },
        "events": {
            "items": [
                {
                    "type": "Normal",
                    "reason": "Started",
                    "involvedObject": {"kind": "Pod", "name": "ssc-webapp-0"},
                    "message": "Container started",
                }
            ]
        },
    }
    return json.dumps(payloads[resource])


if __name__ == "__main__":
    unittest.main()
