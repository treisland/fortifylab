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
    "FORTIFY_SCDAST_IMAGE_TAG",
    "FORTIFY_LIM_CHART_VERSION",
)
DATABASE_KEYS = (
    "FORTIFY_MYSQL_CHART_VERSION",
    "FORTIFY_MYSQL_IMAGE_TAG",
    "FORTIFY_POSTGRES_CHART_VERSION",
    "FORTIFY_POSTGRES_IMAGE_TAG",
)
DISCOVERY_REPOSITORIES = {
    "FORTIFY_SSC_CHART_VERSION": ("fortifydocker/helm-ssc",),
    "FORTIFY_SSC_IMAGE_TAG": ("fortifydocker/ssc-webapp",),
    "FORTIFY_SCSAST_CHART_VERSION": ("fortifydocker/helm-scancentral-sast",),
    "FORTIFY_SCSAST_CTRL_IMAGE_TAG": ("fortifydocker/scancentral-sast-controller",),
    "FORTIFY_SCSAST_WORKER_IMAGE_TAG": ("fortifydocker/scancentral-sast-sensor",),
    "FORTIFY_SCDAST_CHART_VERSION": (
        "fortifydocker/helm-scancentral-dast-core",
        "fortifydocker/helm-scancentral-dast-scanner",
    ),
    "FORTIFY_SCDAST_IMAGE_TAG": (
        "fortifydocker/scancentral-dast-api",
        "fortifydocker/scancentral-dast-globalservice",
        "fortifydocker/dast-scanner",
        "fortifydocker/scancentral-dast-config",
        "fortifydocker/wise",
    ),
    "FORTIFY_LIM_CHART_VERSION": ("fortifydocker/helm-lim",),
}
HELP_EPILOG = """
Command groups:
  Lab operators:
    list, show, compare-env

  Wizard and automation helpers:
    default, env-updates, validate

  Repo-owner curation:
    discover-releases, discover, curate, promote

Common workflows:
  Review curated Flight Plans:
    flight-plans.py list
    flight-plans.py show fortify-26.2

  Compare the current .env to a Flight Plan:
    flight-plans.py compare-env fortify-26.2

  Discover repo-owner release candidates:
    flight-plans.py discover-releases --years 25,26
    flight-plans.py discover --release 26.2
    flight-plans.py curate --years 25,26

  Promote a reviewed candidate:
    flight-plans.py promote tmp/flight-plan-candidates/fortify-26.2.toml --status candidate
    flight-plans.py promote tmp/flight-plan-candidates/fortify-26.2.toml --status recommended --yes

Safety model:
  Read-only:  default, list, show, compare-env, discover-releases without write flags, curate
  Writes tmp: discover, discover-releases --write-complete, discover-releases --write-all
  Writes catalog: promote --yes

Vocabulary:
  Release      A Fortify yy.quarter line such as 25.2 or 26.2 discovered from tags.
  Flight Plan  A curated, deployable bundle of Fortify component versions.
  Candidate    A generated Flight Plan draft that still needs owner review and testing.
"""


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


@dataclass(frozen=True)
class DiscoveryResult:
    selected: dict[str, str]
    warnings: list[str]
    notes: list[str]


@dataclass(frozen=True)
class FamilyScore:
    family: str
    selected: dict[str, str]
    warnings: list[str]
    notes: list[str]

    @property
    def found(self) -> int:
        return sum(1 for key in FORTIFY_KEYS if self.selected.get(key))

    @property
    def total(self) -> int:
        return len(FORTIFY_KEYS)

    @property
    def complete(self) -> bool:
        return self.found == self.total

    @property
    def status(self) -> str:
        return "candidate ready" if self.complete else "needs review"


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
    default_plan = catalog.data.get("default_flight_plan", "")
    if not default_plan:
        issues.append("default_flight_plan is required")
    elif default_plan not in catalog.flight_plans:
        issues.append(f"default_flight_plan {default_plan!r} is not a defined flight plan")
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
        if status in {"recommended", "known-good"}:
            blank = [key for key in FORTIFY_KEYS if key not in missing and not components.get(key)]
            for key in blank:
                issues.append(f"{plan_id}: {key} must not be blank for a {status} plan")
    if recommended != 1:
        issues.append(f"exactly one recommended Flight Plan is required; found {recommended}")
    for key in DATABASE_KEYS:
        if key not in catalog.database_defaults:
            issues.append(f"database_defaults: missing {key}")
    return issues


def validate_catalog_warnings(catalog: Catalog) -> list[str]:
    """Non-fatal review flags: a component version whose release line does not
    match its plan's declared family. Some lag is expected and legitimate (a
    vendor release not yet available for every component), so this never fails
    `validate` or blocks promotion — it only makes the drift visible instead of
    letting it hide behind a clean `validate` result."""
    warnings: list[str] = []
    for plan_id, plan in catalog.flight_plans.items():
        family = str(plan.get("family", ""))
        if not re.fullmatch(r"\d{2,4}\.\d+", family):
            continue
        components = plan.get("components", {})
        for key in FORTIFY_KEYS:
            value = str(components.get(key, ""))
            if not value:
                continue
            component_family = release_family_from_tag(value)
            if component_family and component_family != family:
                warnings.append(
                    f"{plan_id}: {key}={value!r} looks like release {component_family}, "
                    f"not the plan's family {family!r}"
                )
    return warnings


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
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Docker auth endpoint
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            hint = (
                "the found local Docker credential was rejected"
                if credential
                else "no local Docker credential was found (run `docker login`)"
            )
            raise urllib.error.URLError(
                f"Docker registry token request for {repo} was denied ({hint}); "
                f"verify the account has the required Fortify entitlement"
            ) from exc
        raise
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
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Docker registry endpoint
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise urllib.error.URLError(
                    f"Docker registry denied tags/list for {repo} even with an issued token; "
                    f"verify the logged-in account has the required Fortify entitlement"
                ) from exc
            raise
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


def family_tag_candidates(tags: list[dict[str, Any]], family: str) -> set[str]:
    candidates: set[str] = set()
    for record in tags:
        name = str(record.get("name", ""))
        if not name or name == "latest" or not name.startswith(family):
            continue
        # Anchor the match so family "24.4" cannot match a tag like "24.40.1":
        # the character right after the family prefix must end the family
        # segment (end of string, or a "." / "-" separator), not another digit.
        boundary = name[len(family):len(family) + 1]
        if boundary in ("", ".", "-"):
            candidates.add(name)
    return candidates


def best_tag_for_family(tags: list[dict[str, Any]], family: str) -> tuple[str, str]:
    candidates = family_tag_candidates(tags, family)
    if not candidates:
        return "", f"no {family} tag found"
    return sorted(candidates, key=version_sort_key)[-1], ""


def best_shared_tag_for_family(repo_tags: dict[str, list[dict[str, Any]]], family: str) -> tuple[str, str]:
    shared: set[str] | None = None
    missing: list[str] = []
    for repo, tags in repo_tags.items():
        candidates = family_tag_candidates(tags, family)
        if not candidates:
            missing.append(repo)
        shared = candidates if shared is None else shared & candidates
    if missing:
        return "", f"no {family} tag found in {', '.join(missing)}"
    if not shared:
        return "", f"no common {family} tag found across {', '.join(repo_tags)}"
    return sorted(shared, key=version_sort_key)[-1], ""


def toml_quote(value: str) -> str:
    return json.dumps(value)


def release_family_from_tag(tag: str) -> str:
    match = re.match(r"^v?(\d{2,4}\.\d+)(?:[.-]|$)", tag)
    return match.group(1) if match else ""


def candidate_output_path(family: str, output_dir: Path | None = None) -> Path:
    base = output_dir or (repo_root() / "tmp" / "flight-plan-candidates")
    return base / f"fortify-{family}.toml"


def discover_components(catalog: Catalog, family: str, fixture_dir: Path | None) -> DiscoveryResult:
    warnings: list[str] = []
    notes: list[str] = []
    selected: dict[str, str] = {}
    for key in FORTIFY_KEYS:
        repos = DISCOVERY_REPOSITORIES.get(key, ())
        fallback = catalog_fallback_component(catalog, family, key)
        if not repos:
            selected[key] = fallback
            if fallback:
                warnings.append(f"{key}: no Docker repository mapping; reused catalog value {fallback}")
            else:
                warnings.append(f"{key}: no Docker repository mapping; fill manually")
            continue
        try:
            repo_tags: dict[str, list[dict[str, Any]]] = {}
            sources: dict[str, str] = {}
            for repo in repos:
                tags, source = dockerhub_tags(repo, fixture_dir=fixture_dir)
                repo_tags[repo] = tags
                sources[repo] = source
            if len(repos) == 1:
                value, warning = best_tag_for_family(repo_tags[repos[0]], family)
            else:
                value, warning = best_shared_tag_for_family(repo_tags, family)
            registry_repos = [repo for repo, source in sources.items() if source == "Docker Registry API"]
            if registry_repos and value:
                notes.append(f"{key}: selected from authenticated Docker Registry API for {', '.join(registry_repos)}")
            if not value and fallback:
                value = fallback
                warning = f"{warning}; reused catalog value {fallback}" if warning else f"reused catalog value {fallback}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            repo_list = ", ".join(repos)
            if fallback:
                value, warning = fallback, f"discovery failed for {repo_list}; reused catalog value {fallback} ({exc})"
            else:
                value, warning = "", f"discovery failed for {repo_list}: {exc}"
        selected[key] = value
        if warning:
            warnings.append(f"{key}: {warning}")
    return DiscoveryResult(selected=selected, warnings=warnings, notes=notes)


def candidate_lines(family: str, selected: dict[str, str], warnings: list[str], notes: list[str]) -> list[str]:
    lines = [
        "schema_version = 1",
        "",
        f"[flight_plans.{toml_quote('fortify-' + family)}]",
        f"label = {toml_quote('Fortify ' + family)}",
        'status = "candidate"',
        f"family = {toml_quote(family)}",
        'notes = "Generated by Docker/registry discovery. Review and test before promotion."',
        "",
        f"[flight_plans.{toml_quote('fortify-' + family)}.components]",
    ]
    for key in FORTIFY_KEYS:
        lines.append(f"{key} = {toml_quote(selected.get(key, ''))}")
    lines.append("")
    lines.append(f"[flight_plans.{toml_quote('fortify-' + family)}.repositories]")
    for key, repos in DISCOVERY_REPOSITORIES.items():
        lines.append(f"{key} = {toml_quote(", ".join(repos))}")
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
    return lines


def write_candidate(family: str, selected: dict[str, str], warnings: list[str], notes: list[str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(candidate_lines(family, selected, warnings, notes)) + "\n", encoding="utf-8")


def print_candidate_summary(selected: dict[str, str], notes: list[str], warnings: list[str]) -> None:
    print("Candidate components:")
    for key in FORTIFY_KEYS:
        value = selected.get(key, "") or "<review required>"
        print(f"  {key}={value}")
    for note in notes:
        print(f"INFO: {note}")
    for warning in warnings:
        print(f"WARNING: {warning}")


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
    result = discover_components(catalog, family, fixture_dir)
    write_candidate(family, result.selected, result.warnings, result.notes, output)
    print(f"Wrote candidate Flight Plan draft: {output}")
    print_candidate_summary(result.selected, result.notes, result.warnings)
    return 0


def discover_family_scores(catalog: Catalog, fixture_dir: Path | None, years: set[str] | None = None) -> list[FamilyScore]:
    families: set[str] = set()
    for repos in DISCOVERY_REPOSITORIES.values():
        for repo in repos:
            try:
                tags, _source = dockerhub_tags(repo, fixture_dir=fixture_dir)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                continue
            for record in tags:
                family = release_family_from_tag(str(record.get("name", "")))
                if not family:
                    continue
                if years and family.split(".", 1)[0] not in years:
                    continue
                families.add(family)
    for plan in catalog.flight_plans.values():
        family = str(plan.get("family", ""))
        if not re.fullmatch(r"\d{2,4}\.\d+", family):
            continue
        if not years or family.split(".", 1)[0] in years:
            families.add(family)
    scores: list[FamilyScore] = []
    for family in sorted(families, key=version_sort_key, reverse=True):
        result = discover_components(catalog, family, fixture_dir)
        scores.append(FamilyScore(family=family, selected=result.selected, warnings=result.warnings, notes=result.notes))
    return scores


def print_family_scores(scores: list[FamilyScore]) -> None:
    print("Discovered Fortify releases")
    print()
    print(f"  {'Release':<8} {'Coverage':<10} Status")
    for score in scores:
        print(f"  {score.family:<8} {score.found}/{score.total:<8} {score.status}")


def discover_families(catalog: Catalog, years_text: str, min_coverage: int, write_complete: bool, write_all: bool, output_dir: Path | None, fixture_dir: Path | None) -> int:
    years = {item.strip() for item in years_text.split(",") if item.strip()} if years_text else None
    scores = discover_family_scores(catalog, fixture_dir=fixture_dir, years=years)
    if not scores:
        print("No Fortify releases discovered.")
        return 1
    print_family_scores(scores)
    wrote = 0
    for score in scores:
        should_write = write_all or (write_complete and score.found >= min_coverage)
        if not should_write:
            continue
        output = candidate_output_path(score.family, output_dir)
        write_candidate(score.family, score.selected, score.warnings, score.notes, output)
        print(f"Wrote {score.status}: {output}")
        wrote += 1
    if write_complete or write_all:
        print(f"Candidate files written: {wrote}")
    else:
        print()
        print("Next: run discover --release <release> to draft one candidate, or add --write-complete to write complete candidates.")
    return 0


def render_toml_table(name: str, values: dict[str, str]) -> list[str]:
    lines = [f"[{name}]"]
    for key, value in values.items():
        lines.append(f"{key} = {toml_quote(str(value))}")
    return lines


def render_catalog(data: dict[str, Any]) -> str:
    lines = ["schema_version = 1", f"default_flight_plan = {toml_quote(str(data.get('default_flight_plan', '')))}", ""]
    lines.extend(render_toml_table("database_defaults", data.get("database_defaults", {})))
    for plan_id, plan in data.get("flight_plans", {}).items():
        lines.extend(["", f"[flight_plans.{toml_quote(plan_id)}]"])
        for key in ("label", "status", "family", "notes"):
            if key in plan:
                lines.append(f"{key} = {toml_quote(str(plan[key]))}")
        lines.extend(["", f"[flight_plans.{toml_quote(plan_id)}.components]"])
        for key in FORTIFY_KEYS:
            lines.append(f"{key} = {toml_quote(str(plan.get('components', {}).get(key, '')))}")
        repositories = plan.get("repositories", {})
        if repositories:
            lines.extend(["", f"[flight_plans.{toml_quote(plan_id)}.repositories]"])
            for key, repo in repositories.items():
                lines.append(f"{key} = {toml_quote(str(repo))}")
    return "\n".join(lines) + "\n"


def promote_candidate(catalog: Catalog, candidate_path: Path, status: str, set_default: bool, yes: bool) -> int:
    if status not in VALID_STATUSES:
        print(f"ERROR: status must be one of {', '.join(sorted(VALID_STATUSES))}", file=sys.stderr)
        return 1
    candidate = load_catalog(candidate_path)
    if len(candidate.flight_plans) != 1:
        print("ERROR: candidate file must contain exactly one Flight Plan", file=sys.stderr)
        return 1
    plan_id, plan = next(iter(candidate.flight_plans.items()))
    plan = dict(plan)
    plan["status"] = status
    data = dict(catalog.data)
    data["database_defaults"] = dict(catalog.database_defaults)
    plans = {key: dict(value) for key, value in catalog.flight_plans.items()}
    if status == "recommended":
        for existing in plans.values():
            if existing.get("status") == "recommended":
                existing["status"] = "known-good"
    plans[plan_id] = plan
    data["flight_plans"] = plans
    if set_default or status == "recommended":
        data["default_flight_plan"] = plan_id
    promoted = Catalog(path=catalog.path, data=data)
    issues = validate_catalog(promoted)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1
    print(f"Promote candidate: {candidate_path}")
    print(f"Target catalog:    {catalog.path}")
    print(f"Plan:              {plan_id}")
    print(f"Status:            {status}")
    print(f"Default:           {data.get('default_flight_plan', '')}")
    if not yes:
        print("Dry run only. Re-run with --yes to update the catalog.")
        return 0
    backup = catalog.path.with_suffix(catalog.path.suffix + ".bak")
    backup.write_text(catalog.path.read_text(encoding="utf-8"), encoding="utf-8")
    catalog.path.write_text(render_catalog(data), encoding="utf-8")
    print(f"Updated catalog. Backup: {backup}")
    return 0


def curate(catalog: Catalog, years_text: str, fixture_dir: Path | None) -> int:
    years = {item.strip() for item in years_text.split(",") if item.strip()} if years_text else None
    scores = discover_family_scores(catalog, fixture_dir=fixture_dir, years=years)
    if not scores:
        print("No Fortify releases discovered.")
        return 1
    print_family_scores(scores)
    print()
    print("Curator workflow")
    print("  1. Draft:    flight-plans.py discover --release <release>")
    print("  2. Review:   inspect tmp/flight-plan-candidates/fortify-<release>.toml")
    print("  3. Promote:  flight-plans.py promote tmp/flight-plan-candidates/fortify-<release>.toml --status candidate --yes")
    print("  4. Validate: flight-plans.py validate")
    print()
    ready = [score.family for score in scores if score.complete]
    if ready:
        print("Complete candidate releases: " + ", ".join(ready))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=default_catalog_path(), help="Flight Plan catalog path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "validate",
        help="Validate catalog structure and curated plan requirements",
        description="Validate config/flight-plans.toml for required schema, statuses, component keys, and exactly one recommended plan.",
        epilog="""Example:
  flight-plans.py validate

Safety:
  Read-only. Use this before opening or merging a catalog change.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub.add_parser(
        "default",
        help="Print the default Flight Plan id",
        description="Print only the configured default Flight Plan id. This is intended for scripts and wizard integration.",
        epilog="""Example:
  flight-plans.py default

Safety:
  Read-only.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser = sub.add_parser(
        "list",
        help="List curated Flight Plans",
        description="List Flight Plans from the catalog. Candidate plans are hidden by default so normal lab users see only curated choices.",
        epilog="""Examples:
  flight-plans.py list
  flight-plans.py list --include-candidates

Safety:
  Read-only.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument("--include-candidates", action="store_true", help="Include candidate plans normally hidden from lab users")
    show_parser = sub.add_parser(
        "show",
        help="Show one Flight Plan and its component versions",
        description="Show one Flight Plan, including Fortify component versions and the separate database defaults.",
        epilog="""Example:
  flight-plans.py show fortify-26.2

Notes:
  Database versions are shown separately because database upgrade and rollback decisions are not part of a Flight Plan.

Safety:
  Read-only.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument("plan_id")
    updates_parser = sub.add_parser(
        "env-updates",
        help="Print .env updates for a selected Flight Plan",
        description="Print shell-style key=value updates for the Fortify component versions in one Flight Plan. The wizard uses this output to stage .env changes with its normal backup flow.",
        epilog="""Examples:
  flight-plans.py env-updates fortify-26.2
  flight-plans.py env-updates fortify-25.x --include-empty

Safety:
  Read-only. This command prints updates but does not edit .env.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    updates_parser.add_argument("plan_id")
    updates_parser.add_argument("--include-empty", action="store_true", help="Print keys even when the candidate value is blank")
    compare_parser = sub.add_parser(
        "compare-env",
        help="Compare the current .env to a Flight Plan",
        description="Compare Fortify component version values in an .env file against one Flight Plan and report aligned, drifted, or review-required fields.",
        epilog="""Examples:
  flight-plans.py compare-env fortify-26.2
  flight-plans.py compare-env fortify-26.2 --env-file /path/to/.env

Exit codes:
  0  all managed Fortify component values match
  1  one or more managed values drift from the plan

Safety:
  Read-only. Secrets are not printed.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compare_parser.add_argument("plan_id")
    compare_parser.add_argument("--env-file", type=Path, default=repo_root() / ".env", help=".env file to compare; defaults to the repo .env")
    discover_parser = sub.add_parser(
        "discover",
        help="Draft one candidate Flight Plan from a Fortify release",
        description="Discover one Fortify release such as 26.2 and write a candidate Flight Plan TOML file.",
        epilog="""Examples:
  flight-plans.py discover --release 26.2
  flight-plans.py discover --release 25.2 --output tmp/flight-plan-candidates/fortify-25.2.toml

Compatibility:
  --family is accepted as an alias for --release.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    discover_parser.add_argument("--release", "--family", dest="release", required=True, help="Fortify release line such as 25.2 or 26.2")
    discover_parser.add_argument("--output", type=Path)
    discover_parser.add_argument("--fixture-dir", type=Path)
    releases_parser = sub.add_parser(
        "discover-releases",
        aliases=["discover-families"],
        help="Scan Docker tags for Fortify yy.quarter releases",
        description="Scan known Fortify Docker repositories for release lines such as 25.2 or 26.2 and score candidate Flight Plan coverage.",
        epilog="""Examples:
  flight-plans.py discover-releases --years 25,26
  flight-plans.py discover-releases --years 25,26 --write-complete

Compatibility:
  discover-families is accepted as an alias for discover-releases.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    releases_parser.add_argument("--years", default="", help="Comma-separated release years such as 25,26")
    releases_parser.add_argument("--min-coverage", type=int, default=len(FORTIFY_KEYS), help="Minimum discovered component count before --write-complete writes a candidate")
    releases_parser.add_argument("--write-complete", action="store_true", help="Write candidate files for releases meeting --min-coverage")
    releases_parser.add_argument("--write-all", action="store_true", help="Write candidate files for every discovered release, including incomplete ones")
    releases_parser.add_argument("--output-dir", type=Path)
    releases_parser.add_argument("--fixture-dir", type=Path)
    promote_parser = sub.add_parser(
        "promote",
        help="Promote a reviewed candidate into the catalog",
        description="Promote one reviewed candidate Flight Plan into the catalog. Dry run is the default; --yes writes the catalog.",
        epilog="""Examples:
  flight-plans.py promote tmp/flight-plan-candidates/fortify-26.2.toml --status candidate
  flight-plans.py promote tmp/flight-plan-candidates/fortify-26.2.toml --status recommended --yes

Safety:
  --yes writes config/flight-plans.toml and creates a backup.
  --status recommended also updates the default plan and demotes the previous recommended plan.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    promote_parser.add_argument("candidate", type=Path)
    promote_parser.add_argument("--status", choices=sorted(VALID_STATUSES), default="candidate")
    promote_parser.add_argument("--set-default", action="store_true")
    promote_parser.add_argument("--yes", action="store_true")
    curate_parser = sub.add_parser(
        "curate",
        help="Print the repo-owner Flight Plan curation workflow",
        description="Scan release candidates and print the recommended repo-owner workflow for drafting, reviewing, promoting, and validating Flight Plans.",
        epilog="""Examples:
  flight-plans.py curate --years 25,26
  flight-plans.py curate --years 26

Safety:
  Read-only. This command prints guidance and does not write candidate files or the catalog.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    curate_parser.add_argument("--years", default="", help="Comma-separated release years such as 25,26")
    curate_parser.add_argument("--fixture-dir", type=Path)
    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)
    if args.command == "validate":
        issues = validate_catalog(catalog)
        for warning in validate_catalog_warnings(catalog):
            print(f"WARNING: {warning}", file=sys.stderr)
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
        out = args.output or candidate_output_path(args.release)
        return discover(catalog, args.release, out, args.fixture_dir)
    if args.command in {"discover-releases", "discover-families"}:
        return discover_families(catalog, args.years, args.min_coverage, args.write_complete, args.write_all, args.output_dir, args.fixture_dir)
    if args.command == "promote":
        return promote_candidate(catalog, args.candidate, args.status, args.set_default, args.yes)
    if args.command == "curate":
        return curate(catalog, args.years, args.fixture_dir)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
