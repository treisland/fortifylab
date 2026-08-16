#!/usr/bin/env python3
"""FortifyLab Flight Plan catalog and repo-owner discovery helper."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VALID_STATUSES = {"candidate", "known-good", "recommended", "legacy", "deprecated"}
FORTIFY_KEYS = (
    "FORTIFY_SSC_CHART_VERSION",
    "FORTIFY_SSC_IMAGE_TAG",
    "FORTIFY_SCSAST_CHART_VERSION",
    "FORTIFY_SCSAST_CTRL_IMAGE_TAG",
    "FORTIFY_SCSAST_WORKER_IMAGE_TAG",
    "FORTIFY_SCDAST_CHART_VERSION",
    "FORTIFY_LIM_CHART_VERSION",
)
DATABASE_KEYS = (
    "FORTIFY_MYSQL_CHART_VERSION",
    "FORTIFY_MYSQL_IMAGE_TAG",
    "FORTIFY_POSTGRES_CHART_VERSION",
    "FORTIFY_POSTGRES_IMAGE_TAG",
)
DISCOVERY_REPOSITORIES = {
    "FORTIFY_SSC_CHART_VERSION": "fortifydocker/helm-ssc",
    "FORTIFY_SSC_IMAGE_TAG": "fortifydocker/ssc-webapp",
    "FORTIFY_SCSAST_CHART_VERSION": "fortifydocker/helm-scancentral-sast",
    "FORTIFY_SCDAST_CHART_VERSION": "fortifydocker/helm-scancentral-dast-core",
    "FORTIFY_LIM_CHART_VERSION": "fortifydocker/helm-lim",
}


@dataclass(frozen=True)
class Catalog:
    path: Path
    data: dict[str, Any]

    @property
    def flight_plans(self) -> dict[str, Any]:
        return self.data.get("flight_plans", {})

    @property
    def database_defaults(self) -> dict[str, str]:
        return dict(self.data.get("database_defaults", {}))


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_catalog_path() -> Path:
    return repo_root() / "config" / "flight-plans.toml"


def load_catalog(path: Path) -> Catalog:
    with path.open("rb") as handle:
        return Catalog(path=path, data=tomllib.load(handle))


def plan_record(catalog: Catalog, plan_id: str) -> dict[str, Any]:
    try:
        return catalog.flight_plans[plan_id]
    except KeyError as exc:
        raise SystemExit(f"Unknown Flight Plan: {plan_id}") from exc


def validate_catalog(catalog: Catalog) -> list[str]:
    issues: list[str] = []
    if catalog.data.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    if not catalog.flight_plans:
        issues.append("at least one flight plan is required")
    recommended = 0
    for plan_id, plan in catalog.flight_plans.items():
        status = plan.get("status", "")
        label = plan.get("label", "")
        components = plan.get("components", {})
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", plan_id):
            issues.append(f"{plan_id}: id must be lowercase letters, numbers, dot, dash, or underscore")
        if not label:
            issues.append(f"{plan_id}: label is required")
        if status not in VALID_STATUSES:
            issues.append(f"{plan_id}: status must be one of {', '.join(sorted(VALID_STATUSES))}")
        if status == "recommended":
            recommended += 1
        missing = [key for key in FORTIFY_KEYS if key not in components]
        for key in missing:
            issues.append(f"{plan_id}: missing component key {key}")
        for key in components:
            if key not in FORTIFY_KEYS:
                issues.append(f"{plan_id}: unsupported component key {key}")
    if recommended != 1:
        issues.append(f"exactly one recommended Flight Plan is required; found {recommended}")
    for key in DATABASE_KEYS:
        if key not in catalog.database_defaults:
            issues.append(f"database_defaults: missing {key}")
    return issues


def print_list(catalog: Catalog, include_candidates: bool) -> int:
    for plan_id, plan in catalog.flight_plans.items():
        status = plan.get("status", "unknown")
        if status == "candidate" and not include_candidates:
            continue
        print(f"{plan_id}\t{plan.get('label', plan_id)}\t{status}\t{plan.get('family', '')}")
    return 0


def print_show(catalog: Catalog, plan_id: str) -> int:
    plan = plan_record(catalog, plan_id)
    print(f"Flight Plan: {plan.get('label', plan_id)}")
    print(f"ID:          {plan_id}")
    print(f"Status:      {plan.get('status', '<unknown>')}")
    print(f"Family:      {plan.get('family', '<unknown>')}")
    print(f"Notes:       {plan.get('notes', '')}")
    print("Fortify components")
    for key, value in plan.get("components", {}).items():
        print(f"  {key}={value or '<review required>'}")
    print("Database defaults are separate")
    for key, value in catalog.database_defaults.items():
        print(f"  {key}={value}")
    return 0


def print_env_updates(catalog: Catalog, plan_id: str, include_empty: bool) -> int:
    components = plan_record(catalog, plan_id).get("components", {})
    for key in FORTIFY_KEYS:
        value = components.get(key, "")
        if value or include_empty:
            print(f"{key}={value}")
    return 0


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key, raw = match.groups()
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
            raw = raw[1:-1]
        values[key] = raw
    return values


def compare_env(catalog: Catalog, plan_id: str, env_file: Path) -> int:
    env = parse_env_file(env_file)
    components = plan_record(catalog, plan_id).get("components", {})
    mismatch = 0
    for key in FORTIFY_KEYS:
        expected = components.get(key, "")
        if not expected:
            print(f"{key}\tunknown\t<review required>\t{env.get(key, '<unset>')}")
            continue
        current = env.get(key, "")
        state = "aligned" if current == expected else "drifted"
        mismatch += 0 if state == "aligned" else 1
        print(f"{key}\t{state}\t{expected}\t{current or '<unset>'}")
    for key in DATABASE_KEYS:
        print(f"{key}\tdatabase-separate\t{catalog.database_defaults.get(key, '<unknown>')}\t{env.get(key, '<unset>')}")
    return 1 if mismatch else 0


def docker_config_path() -> Path:
    return Path(os.environ.get("DOCKER_CONFIG", Path.home() / ".docker")) / "config.json"


def docker_config() -> dict[str, Any]:
    path = docker_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def docker_registry_hosts(repo: str) -> tuple[str, ...]:
    if "/" not in repo:
        return ("https://index.docker.io/v1/", "registry-1.docker.io", "docker.io")
    return ("https://index.docker.io/v1/", "registry-1.docker.io", "https://registry-1.docker.io/v2/", "docker.io")


def docker_credential_helper_name(config: dict[str, Any], host: str) -> str:
    helpers = config.get("credHelpers", {})
    helper = helpers.get(host)
    if helper:
        return str(helper)
    store = config.get("credsStore")
    return str(store or "")


def docker_credential_from_helper(helper: str, host: str) -> tuple[str, str] | None:
    if not helper:
        return None
    command = f"docker-credential-{helper}"
    try:
        result = subprocess.run(
            [command, "get"],
            input=host,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    username = str(data.get("Username", ""))
    secret = str(data.get("Secret", ""))
    if username and secret:
        return username, secret
    return None


def docker_credential_from_auths(config: dict[str, Any], host: str) -> tuple[str, str] | None:
    auths = config.get("auths", {})
    record = auths.get(host) or auths.get(host.rstrip("/"))
    if not isinstance(record, dict):
        return None
    encoded = str(record.get("auth", ""))
    if not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in decoded:
        return None
    username, secret = decoded.split(":", 1)
    if username and secret:
        return username, secret
    return None


def docker_credential(repo: str) -> tuple[str, str] | None:
    config = docker_config()
    for host in docker_registry_hosts(repo):
        helper = docker_credential_helper_name(config, host)
        credential = docker_credential_from_helper(helper, host)
        if credential:
            return credential
        credential = docker_credential_from_auths(config, host)
        if credential:
            return credential
    return None


def registry_bearer_token(repo: str) -> str:
    credential = docker_credential(repo)
    query = urllib.parse.urlencode({"service": "registry.docker.io", "scope": f"repository:{repo}:pull"})
    request = urllib.request.Request(f"https://auth.docker.io/token?{query}")
    if credential:
        raw = f"{credential[0]}:{credential[1]}".encode("utf-8")
        request.add_header("Authorization", "Basic " + base64.b64encode(raw).decode("ascii"))
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Docker auth endpoint
        data = json.loads(response.read().decode("utf-8"))
    token = str(data.get("token") or data.get("access_token") or "")
    if not token:
        raise urllib.error.URLError("Docker registry token response did not include a token")
    return token


def registry_tags(repo: str, page_size: int = 1000, fixture_dir: Path | None = None) -> list[dict[str, Any]]:
    namespace, name = repo.split("/", 1)
    if fixture_dir:
        fixture = fixture_dir / f"registry__{namespace}__{name}__page1.json"
        if not fixture.exists():
            return []
        data = json.loads(fixture.read_text(encoding="utf-8"))
        return [{"name": tag} for tag in data.get("tags", [])]
    token = registry_bearer_token(repo)
    tags: list[str] = []
    last = ""
    for _ in range(10):
        query = urllib.parse.urlencode({"n": str(page_size), **({"last": last} if last else {})})
        request = urllib.request.Request(f"https://registry-1.docker.io/v2/{repo}/tags/list?{query}")
        request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Docker registry endpoint
            data = json.loads(response.read().decode("utf-8"))
        page_tags = [str(tag) for tag in data.get("tags", []) if tag]
        tags.extend(page_tags)
        if len(page_tags) < page_size:
            break
        last = page_tags[-1]
    return [{"name": tag} for tag in tags]


def dockerhub_api_tags(repo: str, page_size: int = 100, pages: int = 2, fixture_dir: Path | None = None) -> list[dict[str, Any]]:
    namespace, name = repo.split("/", 1)
    records: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        if fixture_dir:
            fixture = fixture_dir / f"{namespace}__{name}__page{page}.json"
            if not fixture.exists():
                break
            data = json.loads(fixture.read_text(encoding="utf-8"))
        else:
            url = f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{name}/tags?page={page}&page_size={page_size}"
            with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - fixed Docker Hub API endpoint
                data = json.loads(response.read().decode("utf-8"))
        records.extend(data.get("results", []))
        if not data.get("next"):
            break
    return records


def dockerhub_tags(repo: str, page_size: int = 100, pages: int = 2, fixture_dir: Path | None = None) -> tuple[list[dict[str, Any]], str]:
    try:
        records = dockerhub_api_tags(repo, page_size=page_size, pages=pages, fixture_dir=fixture_dir)
        if records:
            return records, "Docker Hub API"
    except urllib.error.HTTPError as exc:
        if exc.code not in {401, 403, 404}:
            raise
    records = registry_tags(repo, fixture_dir=fixture_dir)
    if records:
        return records, "Docker Registry API"
    return [], "Docker Hub API"

def version_sort_key(tag: str) -> tuple[Any, ...]:
    pieces = re.split(r"([0-9]+)", tag)
    result: list[Any] = []
    for piece in pieces:
        result.append(int(piece) if piece.isdigit() else piece)
    return tuple(result)


def best_tag_for_family(tags: list[dict[str, Any]], family: str) -> tuple[str, str]:
    candidates: list[str] = []
    for record in tags:
        name = str(record.get("name", ""))
        if not name or name == "latest":
            continue
        if name.startswith(family):
            candidates.append(name)
    if not candidates:
        numeric = [str(record.get("name", "")) for record in tags if re.search(r"\d", str(record.get("name", "")))]
        numeric = [name for name in numeric if name and name != "latest"]
        if not numeric:
            return "", "no numeric tag found"
        return sorted(numeric, key=version_sort_key)[-1], f"no {family} tag found; selected newest numeric candidate"
    return sorted(candidates, key=version_sort_key)[-1], ""


def toml_quote(value: str) -> str:
    return json.dumps(value)


def catalog_fallback_component(catalog: Catalog, family: str, key: str) -> str:
    exact_id = f"fortify-{family}"
    if exact_id in catalog.flight_plans:
        value = str(catalog.flight_plans[exact_id].get("components", {}).get(key, ""))
        if value:
            return value
    for plan in catalog.flight_plans.values():
        if str(plan.get("family", "")) != family:
            continue
        value = str(plan.get("components", {}).get(key, ""))
        if value:
            return value
    return ""


def discover(catalog: Catalog, family: str, output: Path, fixture_dir: Path | None) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "schema_version = 1",
        "",
        f"[flight_plans.{toml_quote('fortify-' + family)}]",
        f"label = {toml_quote('Fortify ' + family)}",
        'status = "candidate"',
        f"family = {toml_quote(family)}",
        'notes = "Generated by Docker Hub discovery. Review and test before promotion."',
        "",
        f"[flight_plans.{toml_quote('fortify-' + family)}.components]",
    ]
    warnings: list[str] = []
    notes: list[str] = []
    selected: dict[str, str] = {}
    for key in FORTIFY_KEYS:
        repo = DISCOVERY_REPOSITORIES.get(key)
        fallback = catalog_fallback_component(catalog, family, key)
        if not repo:
            selected[key] = fallback
            if fallback:
                warnings.append(f"{key}: no Docker repository mapping; reused catalog value {fallback}")
            else:
                warnings.append(f"{key}: no Docker repository mapping; fill manually")
            continue
        try:
            tags, source = dockerhub_tags(repo, fixture_dir=fixture_dir)
            value, warning = best_tag_for_family(tags, family)
            if source == "Docker Registry API" and value:
                notes.append(f"{key}: selected from authenticated {source}")
            if not value and fallback:
                value = fallback
                warning = f"{warning}; reused catalog value {fallback}" if warning else f"reused catalog value {fallback}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            if fallback:
                value, warning = fallback, f"discovery failed for {repo}; reused catalog value {fallback} ({exc})"
            else:
                value, warning = "", f"discovery failed for {repo}: {exc}"
        selected[key] = value
        if warning:
            warnings.append(f"{key}: {warning}")
    for key in FORTIFY_KEYS:
        lines.append(f"{key} = {toml_quote(selected[key])}")
    lines.append("")
    lines.append(f"[flight_plans.{toml_quote('fortify-' + family)}.repositories]")
    for key, repo in DISCOVERY_REPOSITORIES.items():
        lines.append(f"{key} = {toml_quote(repo)}")
    if warnings:
        lines.append("")
        lines.append("# Review warnings")
        for warning in warnings:
            lines.append(f"# - {warning}")
    if notes:
        lines.append("")
        lines.append("# Discovery notes")
        for note in notes:
            lines.append(f"# - {note}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote candidate Flight Plan draft: {output}")
    for note in notes:
        print(f"INFO: {note}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=default_catalog_path())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("default")
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--include-candidates", action="store_true")
    show_parser = sub.add_parser("show")
    show_parser.add_argument("plan_id")
    updates_parser = sub.add_parser("env-updates")
    updates_parser.add_argument("plan_id")
    updates_parser.add_argument("--include-empty", action="store_true")
    compare_parser = sub.add_parser("compare-env")
    compare_parser.add_argument("plan_id")
    compare_parser.add_argument("--env-file", type=Path, default=repo_root() / ".env")
    discover_parser = sub.add_parser("discover")
    discover_parser.add_argument("--family", required=True)
    discover_parser.add_argument("--output", type=Path)
    discover_parser.add_argument("--fixture-dir", type=Path)
    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)
    if args.command == "validate":
        issues = validate_catalog(catalog)
        if issues:
            for issue in issues:
                print(f"ERROR: {issue}", file=sys.stderr)
            return 1
        print(f"Flight Plan catalog valid: {args.catalog}")
        return 0
    if args.command == "default":
        print(catalog.data.get("default_flight_plan", ""))
        return 0
    if args.command == "list":
        return print_list(catalog, args.include_candidates)
    if args.command == "show":
        return print_show(catalog, args.plan_id)
    if args.command == "env-updates":
        return print_env_updates(catalog, args.plan_id, args.include_empty)
    if args.command == "compare-env":
        return compare_env(catalog, args.plan_id, args.env_file)
    if args.command == "discover":
        out = args.output or (repo_root() / "tmp" / "flight-plan-candidates" / f"fortify-{args.family}.toml")
        return discover(catalog, args.family, out, args.fixture_dir)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
