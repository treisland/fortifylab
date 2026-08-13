import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "docs" / "operations"


class OperationsDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.troubleshooting = (OPERATIONS / "troubleshooting.md").read_text(encoding="utf-8")
        cls.lifecycle = (OPERATIONS / "deployment-and-lifecycle.md").read_text(encoding="utf-8")
        cls.recovery = (OPERATIONS / "backup-and-recovery.md").read_text(encoding="utf-8")
        cls.diagnostics = (OPERATIONS / "diagnostics.md").read_text(encoding="utf-8")

    def test_all_required_symptoms_are_covered(self) -> None:
        for phrase in (
            "Pods remain Pending",
            "Pods restart or never become Ready",
            "Image pull failures",
            "Storage and claims",
            "MySQL and SSC",
            "ScanCentral SAST",
            "PostgreSQL, LIM, and ScanCentral DAST",
            "DNS, ingress, URLs, and TLS",
            "Kubernetes Dashboard",
            "Configuration and version drift",
        ):
            self.assertIn(phrase, self.troubleshooting)

    def test_readiness_is_distinguished_from_application_health(self) -> None:
        self.assertIn("Readiness is not application health", self.troubleshooting)
        self.assertIn("application-health", self.lifecycle)

    def test_lifecycle_operations_and_dependency_order_are_explicit(self) -> None:
        for operation in ("Start / Upgrade", "Stop", "Restart", "Repair / retry", "Uninstall", "Delete data"):
            self.assertIn(operation, self.lifecycle)
        self.assertLess(self.lifecycle.index("MySQL and PostgreSQL"), self.lifecycle.index("SSC and LIM"))
        self.assertLess(self.lifecycle.index("SSC and LIM"), self.lifecycle.index("ScanCentral SAST"))
        self.assertLess(self.lifecycle.index("ScanCentral DAST Core"), self.lifecycle.index("ScanCentral DAST scanner"))

    def test_data_safety_boundaries_are_prominent(self) -> None:
        combined = self.troubleshooting + self.lifecycle + self.recovery
        self.assertIn("Never use PVC deletion as routine repair", combined)
        self.assertIn("Do not bypass verification", combined)
        self.assertIn("Destroy (deletes data)", self.lifecycle)
        self.assertIn("matching SSC database and `secret.key`", self.recovery)

    def test_guided_orchestration_contract_is_documented(self) -> None:
        for phrase in (
            "Guided deployment orchestration contract",
            "operation was launched or applied",
            "lifecycle verification passes",
            "Pending",
            "Running",
            "Verifying",
            "Complete",
            "Failed",
            "Skipped",
            "live wait screen",
            "elapsed time",
            "current probe name",
            "workload readiness counts",
            "recent relevant Kubernetes events",
            "interactive takeover",
            "Auto-advance",
            "countdown",
            "Resume",
            "sanitized diagnostics options",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.lifecycle)

    def test_guided_orchestration_needed_hooks_are_tracked(self) -> None:
        for hook in (
            "guided_step_probe",
            "guided_step_timeout",
            "guided_step_in_progress",
            "guided_wait_for_step",
            "guided_run_and_verify",
            "guided_countdown",
            "guided_diagnostics_bundle",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, self.lifecycle)

    def test_diagnostics_contract_matches_implementation_allow_list(self) -> None:
        for filename in (
            "README.txt", "deployment-plan.txt", "doctor-summary.txt",
            "network-diagnostics.txt", "kubernetes-evidence.txt", "wizard-log-excerpt.txt",
        ):
            self.assertIn(filename, self.diagnostics)
        for excluded in ("pod/application logs", "Secret", "ConfigMap data", "environment variables", "command arguments", "license contents"):
            self.assertIn(excluded, self.diagnostics)
        implementation = (ROOT / "scripts" / "lib" / "operational-help.sh").read_text(encoding="utf-8")
        self.assertIn("doctor-summary.txt network-diagnostics.txt kubernetes-evidence.txt wizard-log-excerpt.txt", implementation)

    def test_readme_does_not_request_sensitive_support_artifacts(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Your `.env`", readme)
        self.assertNotIn("kubectl logs --tail", readme)
        self.assertIn("sanitized diagnostics bundle", readme)


if __name__ == "__main__":
    unittest.main()
