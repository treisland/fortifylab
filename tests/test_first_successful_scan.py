import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "operations" / "first-scan.md"
SAMPLE = ROOT / "docs" / "examples" / "sast" / "SyntheticGreeting.java"
EXAMPLE_GENERATOR = ROOT / "docs" / "examples" / "first-scan" / "generate-first-scan-scripts.sh"


class FirstSuccessfulScanDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guide = GUIDE.read_text(encoding="utf-8")

    def test_uses_only_synthetic_inputs_and_requires_dast_authorization(self):
        self.assertIn("SyntheticGreeting.java", self.guide)
        self.assertIn("contains no credentials, proprietary logic", self.guide)
        sample = SAMPLE.read_text(encoding="utf-8")
        self.assertIn('System.out.println("Fortify Lab synthetic sample")', sample)
        self.assertNotRegex(sample.lower(), r"password|token|secret|https?://")
        self.assertIn("Record explicit target authorization", self.guide)
        for item in ("target owner", "authorized time window", "do not scan"):
            self.assertIn(item, self.guide)

    def test_covers_sast_destination_token_submission_and_verification(self):
        for phrase in (
            "Fortify Lab Training",
            "Synthetic",
            "ScanCentralCtrlToken",
            "protected ControllerToken",
            "hidden prompt",
            "submit one scan",
            "Verify the SAST result in SSC",
        ):
            self.assertIn(phrase, self.guide)

    def test_covers_dast_dependencies_conservative_scope_and_verification(self):
        for phrase in (
            "PostgreSQL answers its authenticated query",
            "LIM is reachable",
            "All DAST Core workloads",
            "DAST scanner is registered",
            "one exact host",
            "lowest practical concurrency",
            "Verify the DAST result in SSC",
        ):
            self.assertIn(phrase, self.guide)

    def test_defines_success_as_ssc_visible_results(self):
        self.assertIn("visible in the intended SSC application", self.guide)
        self.assertIn("`Running` pod", self.guide)
        self.assertIn("Zero findings are acceptable", self.guide)
        self.assertIn("no SSC-visible record is not success", self.guide)

    def test_includes_placeholder_command_handoff_examples(self):
        self.assertIn("docs/examples/first-scan", self.guide)
        self.assertIn("first-sast-scan.sh", self.guide)
        self.assertIn("first-dast-scan.sh", self.guide)
        self.assertIn("SSC as the primary result destination", self.guide)
        self.assertIn("FoD only", self.guide)
        self.assertIn("Sample applications", self.guide)
        self.assertIn("JUICE_SHOP_URL", self.guide)
        generator = EXAMPLE_GENERATOR.read_text(encoding="utf-8")
        for placeholder in (
            "SSC_URL",
            "SCSAST_CTRL_URL",
            "SSC_CITOKEN",
            "SCSAST_CLIENT_AUTH_TOKEN",
            "AUTHORIZED_DAST_URL",
            "DAST_AUTHORIZATION_NOTE",
        ):
            self.assertIn(placeholder, generator)
        self.assertIn("FoD is optional", generator)
        self.assertIn("JUICE_SHOP_URL", generator)
        self.assertIn("AUTHORIZED_DAST_URL:=${JUICE_SHOP_URL:-}", generator)
        self.assertNotIn("SSC_CITOKEN=", generator)
        self.assertNotIn("SCSAST_CLIENT_AUTH_TOKEN=", generator)

    def test_links_failure_boundaries_to_troubleshooting(self):
        self.assertGreaterEqual(self.guide.count("troubleshooting.md#"), 10)
        for anchor in (
            "#mysql-and-ssc",
            "#scancentral-sast",
            "#postgresql-lim-and-scancentral-dast",
            "#dns-ingress-urls-and-tls",
        ):
            self.assertIn(anchor, self.guide)


if __name__ == "__main__":
    unittest.main()
