"""Helpers for tests that inspect the wizard source contract."""

from __future__ import annotations

from pathlib import Path
import re


def read_wizard_source(root: Path) -> str:
    """Return the compatibility entrypoint plus sourced wizard modules."""
    parts = [(root / "start_wizard.sh").read_text(encoding="utf-8")]
    module_dir = root / "scripts" / "wizard"
    for module_name in (
        "env.sh",
        "app-registry.sh",
        "operations.sh",
        "guided.sh",
        "runbooks.sh",
        "menu.sh",
    ):
        module = module_dir / module_name
        if module.exists():
            source = module.read_text(encoding="utf-8")
            parts.append(source)
            if module_name == "operations.sh":
                nested_modules = re.findall(
                    r"^\s*((?:operations|flight-plans)/[a-z0-9-]+\.sh)\s*$",
                    source,
                    re.MULTILINE,
                )
                for relative_path in nested_modules:
                    parts.append((module_dir / relative_path).read_text(encoding="utf-8"))
    return "\n".join(parts)
