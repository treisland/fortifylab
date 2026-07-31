"""Contract checks for the zero-to-running operator journey."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = (ROOT / "docs/getting-started/index.md").read_text(encoding="utf-8")


class GettingStartedJourneyTests(unittest.TestCase):
    def test_guide_covers_required_deployment_decisions(self) -> None:
        for phrase in (
            "16 GiB RAM",
            "50 GiB free disk",
            "Docker Hub account",
            "FORTIFY_LICENSE_FILE",
            "Guided deployment",
            "Express deployment",
            "Resume or repair",
            "Kubernetes Dashboard",
            "ScanCentralCtrlToken",
            "LIM_POOL_NAME",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, GUIDE)

    def test_guide_explains_dependency_token_and_safety_contracts(self) -> None:
        for phrase in (
            "authenticated `SELECT 1`",
            "SSC is not changed",
            "One-hour view-only",
            "Persistent administrator",
            "Revoke persistent Dashboard tokens",
            "15–20 minutes",
            "mutation impact",
            "Destroy (deletes data)",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, GUIDE)

    def test_guide_never_embeds_a_real_secret(self) -> None:
        self.assertNotIn("184.33.159.224", GUIDE)
        self.assertNotIn("54.38.220.85", GUIDE)
        self.assertNotIn("fortify.license\n-----", GUIDE)


if __name__ == "__main__":
    unittest.main()
