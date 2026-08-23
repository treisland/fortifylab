"""Unit tests for FlightPlansScreen (post-M6 follow-up, #446)."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.domain.flight_plans import Catalog, load_catalog  # noqa: E402
from fortifylab.services.flight_plan_service import FlightPlanService  # noqa: E402
from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.flight_plans import FlightPlansScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402

_CATALOG_TOML = textwrap.dedent(
    """
    schema_version = 1
    default_flight_plan = "plan-a"

    [database_defaults]
    FORTIFY_MYSQL_CHART_VERSION = "9.0.0"
    FORTIFY_MYSQL_IMAGE_TAG = "8.0.0"
    FORTIFY_POSTGRES_CHART_VERSION = "18.0.0"
    FORTIFY_POSTGRES_IMAGE_TAG = "17.0.0"

    [flight_plans."plan-a"]
    label = "Plan A"
    status = "recommended"
    family = "a"
    notes = "Primary plan."

    [flight_plans."plan-a".components]
    FORTIFY_SSC_CHART_VERSION = "1.0.0"
    FORTIFY_SSC_IMAGE_TAG = "1.0.0"
    FORTIFY_SCSAST_CHART_VERSION = "1.0.0"
    FORTIFY_SCSAST_CTRL_IMAGE_TAG = "1.0.0"
    FORTIFY_SCSAST_WORKER_IMAGE_TAG = "1.0.0"
    FORTIFY_SCDAST_CHART_VERSION = "1.0.0"
    FORTIFY_LIM_CHART_VERSION = "1.0.0"

    [flight_plans."plan-b"]
    label = "Plan B"
    status = "candidate"
    family = "b"
    notes = ""

    [flight_plans."plan-b".components]
    FORTIFY_SSC_CHART_VERSION = ""
    FORTIFY_SSC_IMAGE_TAG = ""
    FORTIFY_SCSAST_CHART_VERSION = ""
    FORTIFY_SCSAST_CTRL_IMAGE_TAG = ""
    FORTIFY_SCSAST_WORKER_IMAGE_TAG = ""
    FORTIFY_SCDAST_CHART_VERSION = ""
    FORTIFY_LIM_CHART_VERSION = ""
    """
)


def _screen_with_catalog(directory: Path, *, env_text: str = "") -> FlightPlansScreen:
    catalog_path = directory / "flight-plans.toml"
    catalog_path.write_text(_CATALOG_TOML, encoding="utf-8")
    env_path = directory / ".env"
    env_path.write_text(env_text, encoding="utf-8")
    service = FlightPlanService(load_catalog(catalog_path))
    return FlightPlansScreen(style=TerminalStyle(color=False, symbols=False), service=service, env_file=env_path)


class FlightPlansScreenTests(unittest.TestCase):
    def test_renders_every_plan_and_marks_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen_with_catalog(Path(directory))
            rendered = screen.render()
            self.assertIn("Plan A", rendered)
            self.assertIn("Plan B", rendered)
            self.assertIn("(default)", rendered)

    def test_enter_views_components_and_env_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen_with_catalog(Path(directory), env_text="FORTIFY_SSC_CHART_VERSION=2.0.0\n")
            screen.handle_event(KeyEvent("enter"))
            self.assertTrue(screen.viewing)
            rendered = screen.render()
            self.assertIn("FORTIFY_SSC_CHART_VERSION", rendered)
            self.assertIn("drifted", rendered)
            self.assertIn("expected=1.0.0", rendered)
            self.assertIn("current=2.0.0", rendered)

    def test_candidate_plan_shows_review_required_for_empty_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen_with_catalog(Path(directory))
            screen.handle_event(KeyEvent("down"))  # -> plan-b (candidate)
            screen.handle_event(KeyEvent("enter"))
            rendered = screen.render()
            self.assertIn("review required", rendered)

    def test_b_returns_to_the_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen_with_catalog(Path(directory))
            screen.handle_event(KeyEvent("enter"))
            screen.handle_event(KeyEvent("b"))
            self.assertFalse(screen.viewing)

    def test_navigation_wraps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen_with_catalog(Path(directory))
            screen.handle_event(KeyEvent("up"))
            self.assertEqual(screen.selected_index, 1)

    def test_q_pops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen_with_catalog(Path(directory))
            command = screen.handle_event(KeyEvent("q"))
            self.assertEqual(command.kind, NavigationKind.POP)

    def test_missing_catalog_file_shows_an_error_not_a_crash(self) -> None:
        import fortifylab.tui.screens.flight_plans as flight_plans_module

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist.toml"
            original = flight_plans_module.default_catalog_path
            flight_plans_module.default_catalog_path = lambda: missing
            try:
                broken = FlightPlansScreen(style=TerminalStyle(color=False, symbols=False))
            finally:
                flight_plans_module.default_catalog_path = original
            self.assertIsNotNone(broken.load_error)
            self.assertIn("Could not load", broken.render())

    def test_unreadable_catalog_path_shows_an_error_not_a_crash(self) -> None:
        # A directory in place of the catalog file raises IsADirectoryError
        # (an OSError, not a FileNotFoundError) when opened -- same family
        # as a permission-denied catalog. This must surface as load_error,
        # not escape __post_init__ and crash the screen.
        import fortifylab.tui.screens.flight_plans as flight_plans_module

        with tempfile.TemporaryDirectory() as directory:
            not_a_file = Path(directory) / "flight-plans.toml"
            not_a_file.mkdir()
            original = flight_plans_module.default_catalog_path
            flight_plans_module.default_catalog_path = lambda: not_a_file
            try:
                broken = FlightPlansScreen(style=TerminalStyle(color=False, symbols=False))
            finally:
                flight_plans_module.default_catalog_path = original
            self.assertIsNotNone(broken.load_error)
            self.assertIn("Could not load", broken.render())

    def test_real_repo_catalog_loads_without_crashing(self) -> None:
        # Uses the actual default_catalog_path()/merged_read_catalog() path
        # (the default when no service is injected), against the real
        # committed config/flight-plans.toml.
        screen = FlightPlansScreen(style=TerminalStyle(color=False, symbols=False))
        self.assertIsNone(screen.load_error)
        rendered = screen.render()
        self.assertIn("Flight Plans", rendered)


if __name__ == "__main__":
    unittest.main()
