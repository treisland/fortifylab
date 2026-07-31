#!/usr/bin/env python3
"""Offline documentation quality and secret-safety checks."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
FENCE = re.compile(r"^```\s*([\w+-]*)\s*$")
NAV_ENTRY = re.compile(r"(?<![\w./-])([A-Za-z0-9_./-]+\.md)(?![\w./-])")
FORBIDDEN_FILES = re.compile(
    r"(?:^|/)(?:secrets/input/(?!README\.md)[^/]+|generated/[^/]+)$"
    r"|\.(?:key|pem|p12|pfx|jks|license)$",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{20,}\b")),
    ("Kubernetes service-account token", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b")),
    ("assigned secret", re.compile(r"(?i)\b(?:password|passwd|token|secret|api[_-]?key)\s*[=:]\s*['\"]?(?!<|\$|\{|example|replace|redacted|your-)[A-Za-z0-9/+_.-]{12,}")),
)
TERMINOLOGY = {
    r"\bScan Central\b": "ScanCentral",
    r"\bFortifyLab\b": "Fortify Lab",
    r"\bKubernetes dashboard\b": "Kubernetes Dashboard",
    r"\bevidance\b": "evidence",
    r"\bdependancies\b": "dependencies",
    r"\bprerequisits?\b": "prerequisite/prerequisites",
}
MERMAID_STARTS = {"flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram", "journey", "gantt", "pie", "mindmap", "timeline", "quadrantChart", "gitGraph"}


def slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*_~]", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def headings(path: Path) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            base = slug(match.group(1))
            count = counts.get(base, 0)
            found.add(base if count == 0 else f"{base}_{count}")
            counts[base] = count + 1
    return found


def markdown_quality(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        errors.append(f"{path.relative_to(ROOT)}: Markdown must start with one H1")
    if sum(line.startswith("# ") for line in lines) != 1:
        errors.append(f"{path.relative_to(ROOT)}: Markdown must contain exactly one H1")
    fence_language: str | None = None
    fence_start = 0
    fence_body: list[str] = []
    for number, line in enumerate(lines, 1):
        if line.rstrip() != line:
            errors.append(f"{path.relative_to(ROOT)}:{number}: trailing whitespace")
        if "\t" in line:
            errors.append(f"{path.relative_to(ROOT)}:{number}: tab character")
        match = FENCE.match(line)
        if match:
            if fence_language is None:
                fence_language = match.group(1)
                fence_start = number
                fence_body = []
                if not fence_language:
                    errors.append(f"{path.relative_to(ROOT)}:{number}: fenced code block needs a language")
            else:
                if fence_language == "mermaid":
                    validate_mermaid(path, fence_start, fence_body, errors)
                elif fence_language in {"bash", "sh", "shell"}:
                    validate_shell(path, fence_start, fence_body, errors)
                fence_language = None
            continue
        if fence_language is not None:
            fence_body.append(line)
    if fence_language is not None:
        errors.append(f"{path.relative_to(ROOT)}:{fence_start}: unclosed code fence")


def validate_shell(path: Path, line: int, body: list[str], errors: list[str]) -> None:
    source = "\n".join(body) + "\n"
    result = subprocess.run(["bash", "-n"], input=source, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1]
        errors.append(f"{path.relative_to(ROOT)}:{line}: unsafe/invalid shell example: {detail}")
    if re.search(r"(?:^|\s)(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", source):
        errors.append(f"{path.relative_to(ROOT)}:{line}: pipe-to-shell example is not allowed")
    if re.search(r"\brm\s+-[^\n]*r[^\n]*f|\bkubectl\s+delete\s+(?:namespace|pvc)\b", source):
        errors.append(f"{path.relative_to(ROOT)}:{line}: destructive command requires a separately reviewed exception")


def validate_mermaid(path: Path, line: int, body: list[str], errors: list[str]) -> None:
    meaningful = [item.strip() for item in body if item.strip() and not item.lstrip().startswith("%%")]
    if not meaningful:
        errors.append(f"{path.relative_to(ROOT)}:{line}: empty Mermaid diagram")
        return
    first = meaningful[0].split()[0]
    if first not in MERMAID_STARTS:
        errors.append(f"{path.relative_to(ROOT)}:{line}: unsupported Mermaid declaration {first!r}")
    joined = "\n".join(meaningful)
    for opening, closing in (("[", "]"), ("(", ")"), ("{", "}")):
        if joined.count(opening) != joined.count(closing):
            errors.append(f"{path.relative_to(ROOT)}:{line}: unbalanced Mermaid {opening}{closing}")


def validate_links(paths: list[Path], errors: list[str]) -> None:
    anchor_cache: dict[Path, set[str]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            target = target.strip().split()[0].strip("<>")
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            filename, _, fragment = unquote(target).partition("#")
            destination = path if not filename else (path.parent / filename).resolve()
            try:
                destination.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)}: link escapes repository: {target}")
                continue
            if not destination.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing link target: {target}")
            elif fragment and destination.suffix.lower() == ".md":
                available = anchor_cache.setdefault(destination, headings(destination))
                if fragment not in available:
                    errors.append(f"{path.relative_to(ROOT)}: missing anchor: {target}")


def shell_array(text: str, name: str) -> list[str]:
    match = re.search(rf"^{name}=\(\n(.*?)\n\)$", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    # A route may contain a Markdown anchor beginning with '#'; it is data, not
    # a shell comment. The registry intentionally contains no inline comments.
    return shlex.split(match.group(1), comments=False)


def validate_wizard_topics(errors: list[str]) -> None:
    registry = (ROOT / "scripts/lib/help.sh").read_text(encoding="utf-8")
    topic_ids = shell_array(registry, "HELP_TOPIC_ID")
    labels = shell_array(registry, "HELP_TOPIC_LABEL")
    files = shell_array(registry, "HELP_TOPIC_FILE")
    routes = shell_array(registry, "HELP_TOPIC_ROUTE")
    if not topic_ids or len(topic_ids) != len(files) or len(topic_ids) != len(routes):
        errors.append("scripts/lib/help.sh: wizard topic ID/file/route arrays are missing or misaligned")
        return
    if not labels or len(labels) > len(topic_ids):
        errors.append("scripts/lib/help.sh: interactive wizard labels are missing or misaligned")
    if len(topic_ids) != len(set(topic_ids)):
        errors.append("scripts/lib/help.sh: wizard topic IDs must be unique")
    for topic_id, offline_file, route in zip(topic_ids, files, routes):
        if not (ROOT / "docs/help" / offline_file).is_file():
            errors.append(f"scripts/lib/help.sh: {topic_id} has missing offline file {offline_file}")
        route_path, _, fragment = route.partition("#")
        if route_path == "index.html":
            online = DOCS / "index.md"
        elif route_path.endswith("/"):
            stem = route_path.rstrip("/")
            page_file = DOCS / f"{stem}.md"
            online = page_file if page_file.is_file() else DOCS / stem / "index.md"
        else:
            online = DOCS / route_path
        if not online.is_file():
            errors.append(f"scripts/lib/help.sh: {topic_id} has missing online route {route}")
        elif fragment and fragment not in headings(online):
            errors.append(f"scripts/lib/help.sh: {topic_id} has missing online anchor {route}")


def validate_nav(paths: list[Path], errors: list[str]) -> None:
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    entries = NAV_ENTRY.findall(config)
    if len(entries) != len(set(entries)):
        errors.append("mkdocs.yml: navigation contains duplicate pages")
    for entry in entries:
        if not (DOCS / entry).is_file():
            errors.append(f"mkdocs.yml: navigation target does not exist: {entry}")
    expected = {path.relative_to(DOCS).as_posix() for path in paths}
    missing = sorted(expected - set(entries))
    if missing:
        errors.append("mkdocs.yml: Markdown pages absent from navigation: " + ", ".join(missing))


def validate_sensitive_content(paths: list[Path], errors: list[str]) -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    for filename in tracked:
        if FORBIDDEN_FILES.search(filename):
            errors.append(f"{filename}: protected/generated secret input must not be tracked")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{path.relative_to(ROOT)}: possible {name}; use an obvious placeholder")
        for bad, preferred in TERMINOLOGY.items():
            match = re.search(bad, text)
            if match:
                line = text[: match.start()].count("\n") + 1
                errors.append(f"{path.relative_to(ROOT)}:{line}: use {preferred!r}, not {match.group()!r}")
        for image in re.findall(r"!\[[^]]*\]\(([^)]+)\)", text):
            if not image.startswith(("https://", "http://")):
                errors.append(f"{path.relative_to(ROOT)}: screenshot/image {image!r} requires secret-safety review")


def main() -> int:
    paths = sorted(DOCS.rglob("*.md"))
    errors: list[str] = []
    for path in paths:
        markdown_quality(path, errors)
    validate_links(paths, errors)
    validate_nav(paths, errors)
    validate_wizard_topics(errors)
    validate_sensitive_content(paths, errors)
    if errors:
        print("Documentation quality gates failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Documentation quality gates passed ({len(paths)} Markdown pages checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
