"""Sanitized diagnostics bundle writer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import tarfile
import tempfile


SENSITIVE_RE = re.compile(r"(?i)(pass|password|token|secret|credential|license|private key|authorization)")


@dataclass(frozen=True)
class DiagnosticsBundle:
    path: Path
    files: tuple[str, ...]


def sanitize_text(text: str) -> str:
    sanitized: list[str] = []
    for line in text.splitlines():
        if SENSITIVE_RE.search(line):
            sanitized.append("<redacted sensitive diagnostic line>")
        else:
            sanitized.append(line)
    return "\n".join(sanitized) + ("\n" if text.endswith("\n") else "")


def write_bundle(output_dir: Path | str, files: dict[str, str]) -> DiagnosticsBundle:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    bundle_path = output / "fortifylab-diagnostics.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        written: list[str] = []
        for relative, content in files.items():
            safe_relative = relative.strip("/").replace("..", "_")
            target = root / safe_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sanitize_text(content), encoding="utf-8")
            written.append(safe_relative)
        metadata = root / "metadata.json"
        metadata.write_text(json.dumps({"files": sorted(written), "sanitized": True}, indent=2), encoding="utf-8")
        written.append("metadata.json")
        with tarfile.open(bundle_path, "w:gz") as archive:
            for relative in written:
                archive.add(root / relative, arcname=relative)
    return DiagnosticsBundle(path=bundle_path, files=tuple(sorted(written)))
