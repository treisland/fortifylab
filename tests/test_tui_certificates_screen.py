"""Unit tests for CertificatesScreen (#446 slice 5)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.tui.events import KeyEvent  # noqa: E402
from fortifylab.tui.screens.base import NavigationKind  # noqa: E402
from fortifylab.tui.screens.certificates import CertificatesScreen  # noqa: E402
from fortifylab.tui.theme import TerminalStyle  # noqa: E402


def _screen(*, env_text: str | None = None, env_dir: Path | None = None) -> CertificatesScreen:
    kwargs = {"style": TerminalStyle(color=False, symbols=False)}
    if env_dir is not None:
        env_path = env_dir / ".env"
        if env_text is not None:
            env_path.write_text(env_text, encoding="utf-8")
        kwargs["env_file"] = env_path
    return CertificatesScreen(**kwargs)


class CertificatesScreenTests(unittest.TestCase):
    def test_renders_root_ca_path_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(
                env_text="ROOTCA_CERT=/opt/fortifylab/certs/rootCA.pem\nDOMAIN=example.com\n",
                env_dir=Path(directory),
            )
            rendered = screen.render()
            self.assertIn("/opt/fortifylab/certs/rootCA.pem", rendered)

    def test_falls_back_to_fortify_certs_default_when_rootca_cert_unset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(
                env_text="FORTIFY_CERTS=/opt/fortifylab/certs\nDOMAIN=example.com\n",
                env_dir=Path(directory),
            )
            rendered = screen.render()
            self.assertIn("/opt/fortifylab/certs/rootCA.pem", rendered)

    def test_missing_env_file_shows_unset_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(env_dir=Path(directory))
            self.assertIn("<unset>", screen.render())

    def test_root_ca_falls_back_to_bash_default_when_both_unset(self) -> None:
        # Bash: ${ROOTCA_CERT:-$FORTIFY_CERTS/rootCA.pem} -- with neither
        # variable set, $FORTIFY_CERTS expands to empty, yielding
        # "/rootCA.pem", not a placeholder like "<unset>/rootCA.pem".
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(env_dir=Path(directory))
            rendered = screen.render()
            self.assertIn("\n  /rootCA.pem\n", rendered)
            self.assertNotIn("<unset>/rootCA.pem", rendered)

    def test_renders_all_lab_hostnames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(env_text="DOMAIN=example.com\n", env_dir=Path(directory))
            rendered = screen.render()
            for prefix in ("ssc", "lim", "sast", "dast", "dashboard"):
                self.assertIn(f"{prefix}.example.com", rendered)

    def test_never_renders_the_private_key_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screen = _screen(
                env_text="ROOTCA_CERT=/opt/fortifylab/certs/rootCA.pem\n"
                "ROOTCA_KEY=/opt/fortifylab/certs/rootCA-key.pem\n"
                "DOMAIN=example.com\n",
                env_dir=Path(directory),
            )
            self.assertNotIn("rootCA-key.pem", screen.render())

    def test_q_pops(self) -> None:
        screen = _screen()
        command = screen.handle_event(KeyEvent("q"))
        self.assertEqual(command.kind, NavigationKind.POP)


if __name__ == "__main__":
    unittest.main()
