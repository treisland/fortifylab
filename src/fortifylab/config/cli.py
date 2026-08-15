"""CLI commands for the Python configuration engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .envfile import EnvUpdate, preview_changes
from .repair import HOST_KEYS, URL_KEYS, domain_url_updates, expected_host, expected_url, validate_hosts_and_urls
from .store import ConfigStore


def configure_parser(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="config_command", metavar="CONFIG_COMMAND")
    diagnostics = _add_env_command(subcommands, "diagnostics", "show derived host and URL diagnostics")
    diagnostics.add_argument("--json", action="store_true", help="emit diagnostics as JSON")
    _add_env_command(subcommands, "validate", "validate derived host and URL values")
    repair = _add_env_command(subcommands, "repair-derived", "repair derived host and URL values from DOMAIN")
    repair.add_argument("--domain", help="domain to repair from; defaults to DOMAIN in the .env file")
    repair.add_argument("--apply", action="store_true", help="write the repair with a backup")
    _add_env_command(subcommands, "backup", "create a timestamped .env backup").add_argument(
        "--reason", default="manual-backup", help="backup reason recorded in metadata"
    )
    _add_env_command(subcommands, "rollback", "restore the last rollback target")
    diff = _add_env_command(subcommands, "diff", "preview assignment changes")
    diff.add_argument("assignments", nargs="*", help="KEY=value assignments to preview")


def run(args: argparse.Namespace) -> int:
    if not getattr(args, "config_command", None):
        print("Python config command shell is available. Choose diagnostics, validate, repair-derived, backup, rollback, or diff.")
        return 0

    store = ConfigStore(Path(args.env))
    if args.config_command == "diagnostics":
        return _diagnostics(store, as_json=args.json)
    if args.config_command == "validate":
        issues = validate_hosts_and_urls(store.load())
        if issues:
            for issue in issues:
                print(issue)
            return 1
        print("Configuration host and URL values look valid.")
        return 0
    if args.config_command == "repair-derived":
        return _repair_derived(store, domain=args.domain, apply=args.apply)
    if args.config_command == "backup":
        backup = store.prepare_backup(args.reason)
        print(f"Backup created: {backup}")
        return 0
    if args.config_command == "rollback":
        restored = store.rollback_last()
        print(f"Restored .env from {restored}")
        return 0
    if args.config_command == "diff":
        updates = tuple(EnvUpdate.parse(assignment) for assignment in args.assignments)
        for line in preview_changes(store.load(), updates):
            print(line)
        return 0
    raise ValueError(f"Unsupported config command: {args.config_command}")


def _add_env_command(subcommands: argparse._SubParsersAction[argparse.ArgumentParser], name: str, help_text: str) -> argparse.ArgumentParser:
    command = subcommands.add_parser(name, help=help_text)
    command.add_argument("--env", default=".env", help="path to the .env file")
    return command


def _diagnostics(store: ConfigStore, *, as_json: bool) -> int:
    document = store.load()
    values = document.values()
    domain = values.get("DOMAIN", "fortifydemo.com")
    rows = []
    for key in (*HOST_KEYS, *URL_KEYS):
        rows.append(
            {
                "key": key,
                "raw": document.raw_value(key) or "<missing>",
                "effective": values.get(key, "<unset>"),
                "expected": expected_host(key, domain) or expected_url(key, domain) or "<none>",
            }
        )
    issues = validate_hosts_and_urls(document)
    if as_json:
        print(json.dumps({"env_file": str(store.env_file), "domain": values.get("DOMAIN"), "values": rows, "issues": issues}, indent=2))
        return 0
    print(f".env file: {store.env_file}")
    print(f"DOMAIN:   {values.get('DOMAIN', '<unset>')}")
    print("\nHost and URL values")
    for row in rows:
        print(f"  {row['key']:<16} raw={row['raw']:<36} effective={row['effective']:<36} expected={row['expected']}")
    print("\nIssues")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("  No host/URL configuration drift detected.")
    return 0


def _repair_derived(store: ConfigStore, *, domain: str | None, apply: bool) -> int:
    document = store.load()
    values = document.values()
    repair_domain = (domain or values.get("DOMAIN") or "fortifydemo.com").lower()
    updates = domain_url_updates(repair_domain)
    for line in preview_changes(document, updates):
        print(line)
    if apply:
        backup = store.apply("repair-domain-url", updates)
        print(f"Updated .env. Backup: {backup}")
    else:
        print("Dry run; no changes written. Add --apply to update .env with a backup.")
    return 0
