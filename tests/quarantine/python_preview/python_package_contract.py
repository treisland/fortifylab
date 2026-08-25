"""Contracts for the Fortify Lab Python package foundation."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class PythonPackageContractTests(unittest.TestCase):
    def test_package_imports_from_src(self) -> None:
        code = "import fortifylab; print(fortifylab.__version__)"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3.1.0-preview", result.stdout)

    def test_clone_and_run_wrapper_exists_and_is_executable(self) -> None:
        wrapper = ROOT / "bin" / "fortifylab"
        self.assertTrue(wrapper.is_file())
        self.assertTrue(os.access(wrapper, os.X_OK))
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH", text)
        self.assertIn("python3 -m fortifylab", text)

    def test_runtime_dependency_metadata_is_conservative_and_separate(self) -> None:
        requirements = (ROOT / "requirements-python.txt").read_text(encoding="utf-8")
        docs_requirements = (ROOT / "requirements-docs.txt").read_text(encoding="utf-8")
        for package in ("typer", "rich", "pydantic", "textual"):
            with self.subTest(package=package):
                self.assertIn(package, requirements.lower())
        self.assertIn("standard library", requirements)
        self.assertNotIn("mkdocs", requirements.lower())
        self.assertIn("mkdocs", docs_requirements.lower())

    def test_readme_documents_python_runtime_dependency_posture(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("requirements-python.txt", readme)
        self.assertIn("requirements-docs.txt", readme)
        self.assertIn("Bash remains the production guided wizard", readme)
        self.assertIn("standard library only", readme)


if __name__ == "__main__":
    unittest.main()
