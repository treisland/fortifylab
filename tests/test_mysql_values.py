"""Contracts for the MySQL Helm values used by SSC."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "apps/mysql/values.yaml"


class MySQLValuesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.values = VALUES.read_text(encoding="utf-8")

    def test_persistence_uses_bitnami_enabled_key(self) -> None:
        self.assertIn("    enabled: true", self.values)
        self.assertNotIn("    enable: true", self.values)

    def test_mysql_pod_is_not_best_effort(self) -> None:
        self.assertIn("  resources:\n    requests:\n      cpu: 250m\n      memory: 1Gi", self.values)

    def test_mysql_probes_allow_slow_persisted_startup(self) -> None:
        for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
            with self.subTest(probe=probe):
                section_start = self.values.index(f"  {probe}:")
                section = self.values[section_start:self.values.index("  configuration:", section_start)]
                self.assertIn("    enabled: true", section)
                self.assertIn("    timeoutSeconds: 10", section)
        self.assertIn("  startupProbe:\n    enabled: true", self.values)
        self.assertIn("    failureThreshold: 60", self.values)


if __name__ == "__main__":
    unittest.main()
