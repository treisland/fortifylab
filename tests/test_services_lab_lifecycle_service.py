"""Unit tests for fortifylab.services.lab_lifecycle_service (deployment &
component management parity: bulk shutdown/start)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.operations import OperationCatalog  # noqa: E402
from fortifylab.services.lab_lifecycle_service import (  # noqa: E402
    active_profile_id,
    apps_for_scope,
    build_lifecycle_plan,
)


class ActiveProfileIdTests(unittest.TestCase):
    def test_defaults_to_full_lab_when_env_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(active_profile_id(Path(directory) / ".env"), "full_lab")

    def test_reads_fortify_deployment_profile_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("FORTIFY_DEPLOYMENT_PROFILE=ssc_only\n", encoding="utf-8")
            self.assertEqual(active_profile_id(env_file), "ssc_only")


class AppsForScopeTests(unittest.TestCase):
    def test_all_scope_returns_every_known_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            apps = apps_for_scope("all", env_file=Path(directory) / ".env")
            self.assertEqual(set(apps), {"mysql", "postgresql", "ssc", "lim", "juice-shop", "webgoat", "dvwa"})

    def test_selected_scope_for_ssc_only_profile_excludes_lim_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("FORTIFY_DEPLOYMENT_PROFILE=ssc_only\n", encoding="utf-8")
            apps = apps_for_scope("selected", env_file=env_file)
            self.assertIn("ssc", apps)
            self.assertIn("mysql", apps)  # ssc pulls in mysql
            self.assertNotIn("lim", apps)
            self.assertNotIn("juice-shop", apps)

    def test_selected_scope_for_sample_apps_profile_is_only_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("FORTIFY_DEPLOYMENT_PROFILE=sample_apps\n", encoding="utf-8")
            apps = apps_for_scope("selected", env_file=env_file)
            self.assertEqual(set(apps), {"juice-shop", "webgoat", "dvwa"})


class BuildLifecyclePlanTests(unittest.TestCase):
    def test_start_all_runs_in_dependency_safe_forward_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = build_lifecycle_plan("start", "all", catalog=OperationCatalog(), env_file=Path(directory) / ".env")
            step_ids = [step.step_id for step in plan.steps]
            self.assertLess(step_ids.index("mysql"), step_ids.index("ssc"))
            self.assertEqual(plan.validate(), ())

    def test_shutdown_all_runs_in_reverse_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = build_lifecycle_plan("shutdown", "all", catalog=OperationCatalog(), env_file=Path(directory) / ".env")
            step_ids = [step.step_id for step in plan.steps]
            self.assertGreater(step_ids.index("mysql"), step_ids.index("ssc"))

    def test_steps_use_the_real_start_or_stop_script_via_bash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = build_lifecycle_plan("start", "all", catalog=OperationCatalog(), env_file=Path(directory) / ".env")
            mysql_step = next(step for step in plan.steps if step.step_id == "mysql")
            self.assertEqual(mysql_step.command, ("bash", "./apps/mysql/start.sh"))

    def test_shutdown_selected_uses_stop_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("FORTIFY_DEPLOYMENT_PROFILE=ssc_only\n", encoding="utf-8")
            plan = build_lifecycle_plan("shutdown", "selected", catalog=OperationCatalog(), env_file=env_file)
            ssc_step = next(step for step in plan.steps if step.step_id == "ssc")
            self.assertEqual(ssc_step.command, ("bash", "./apps/ssc/stop.sh"))

    def test_plan_name_reflects_action_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = build_lifecycle_plan("start", "all", catalog=OperationCatalog(), env_file=Path(directory) / ".env")
            self.assertIn("start", plan.name)
            self.assertIn("all apps", plan.name)

    def test_no_destroy_action_is_ever_produced(self) -> None:
        # Structural guard: this module only ever knows "start"/"shutdown"
        # (mapped to start/stop scripts) -- there is no code path here
        # that could accidentally wire up a destroy script.
        with tempfile.TemporaryDirectory() as directory:
            plan = build_lifecycle_plan("shutdown", "all", catalog=OperationCatalog(), env_file=Path(directory) / ".env")
            for step in plan.steps:
                self.assertNotIn("destroy", " ".join(step.command))


if __name__ == "__main__":
    unittest.main()
