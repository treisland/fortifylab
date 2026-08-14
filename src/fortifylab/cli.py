"""Clone-and-run Python CLI shell for Fortify Lab Phase 3."""

from __future__ import annotations

import argparse
import sys

from .bootstrap import run_bootstrap_checks
from .config.cli import configure_parser as configure_config_parser, run as run_config_command
from .diagnostics import ClusterCollector, write_bundle
from .operations import OperationCatalog, OperationRunner
from .orchestration import BashOperationAdapter
from .runtime import compatibility_report, render_compatibility_report, runtime_paths, write_runtime_log
from .tui import build_demo_snapshot, build_profile, render_guided_step
from .version import __version__
from .web import WebConsoleApp, WebConsoleConfig

_COMMAND_MESSAGES = {
    "doctor": "Python doctor command shell is available; Bash adapter is not wired yet.",
    "config": "Python config command shell is available; config engine lands in Phase 3.4.",
    "deploy": "Python deploy command shell is available; orchestration lands in Phase 3.3.",
    "logs": "Python logs command shell is available; log replacement lands in Phase 3.6.",
    "runbook": "Python runbook command shell is available; safe runner lands in Phase 3.6.",
    "tui": "Python guided TUI command shell is available; prototype lands in Phase 3.2.",
    "web": "Python companion web console preview is available; server hardening lands in Phase 3.8.",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fortifylab",
        description="Fortify Lab Python CLI preview for clone-and-run lab operators.",
    )
    parser.add_argument("--version", action="version", version=f"fortifylab {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, message in _COMMAND_MESSAGES.items():
        sub = subparsers.add_parser(name, help=message)
        sub.set_defaults(message=message)
        if name == "doctor":
            sub.add_argument("--environment", action="store_true", help="run clone-and-run bootstrap and migration checks")
            sub.add_argument("--compatibility", action="store_true", help="run read-only migration compatibility checks")
            sub.add_argument(
                "--collect",
                action="store_true",
                help="run read-only Kubernetes and Helm diagnostics collectors",
            )
            sub.add_argument(
                "--bundle-dir",
                help="write a sanitized diagnostics bundle to this directory",
            )
        if name == "config":
            configure_config_parser(sub)
        if name == "deploy":
            sub.add_argument(
                "--plan",
                metavar="PROFILE",
                help="print the Python orchestration plan for a deployment profile without running it",
            )
            sub.add_argument("--operation", choices=("certs", "secrets", "ssc-start", "ssc-stop", "ssc-destroy"), help="preview or run a Bash-backed operation")
            sub.add_argument("--execute", action="store_true", help="execute a mutating operation instead of dry-running it")
        if name == "logs":
            sub.add_argument("--pod", help="print the kubectl logs command for a pod, or execute it")
            sub.add_argument("--follow", action="store_true", help="follow pod logs")
        if name == "runbook":
            sub.add_argument("--preview", help="preview a runbook path with the safe runner")
        if name == "web":
            sub.add_argument("--check", action="store_true", help="validate web console access-control settings")
            sub.add_argument("--bind", default="127.0.0.1", help="web console bind host")
            sub.add_argument("--allow-lan", action="store_true", help="allow LAN binding when an access token is configured")
            sub.add_argument("--token", help="web console access token")
        if name == "tui":
            sub.add_argument(
                "--demo-screen",
                action="store_true",
                help="render a deterministic guided deployment prototype screen",
            )
    return parser


def adapter_step_ids() -> set[str]:
    return {
        "certs",
        "dashboard",
        "secrets",
        "mysql",
        "postgresql",
        "ssc",
        "lim",
        "sast_controller",
        "sast_sensor",
        "dast_core",
        "dast_scanner",
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "doctor" and args.environment:
        log_file = write_runtime_log("doctor --environment started", event="doctor.environment")
        checks = run_bootstrap_checks()
        for check in checks:
            state = "ok" if check.ok else "failed"
            print(f"{check.name}: {state} - {check.detail}")
        print(f"runtime-log: ok - {log_file}")
        return 0 if all(check.ok for check in checks) else 1
    if args.command == "doctor" and args.compatibility:
        write_runtime_log("doctor --compatibility started", event="doctor.compatibility")
        for line in render_compatibility_report(compatibility_report()):
            print(line)
        print(f"runtime-log: {runtime_paths().log_file}")
        return 0
    if args.command == "doctor" and args.collect:
        results = ClusterCollector().collect()
        for result in results:
            state = "ok" if result.ok else "failed"
            print(f"{result.name}: {state}")
        return 0
    if args.command == "doctor" and args.bundle_dir:
        bundle = write_bundle(
            args.bundle_dir,
            {
                "README.txt": "Fortify Lab sanitized diagnostics bundle.\n",
                "summary.txt": "Generated by fortifylab doctor --bundle-dir. Secrets are redacted.\n",
            },
        )
        print(f"Diagnostics bundle: {bundle.path}")
        return 0
    if args.command == "config":
        return run_config_command(args)
    if args.command == "deploy" and args.operation:
        catalog = OperationCatalog()
        operations = {
            "certs": catalog.certs(),
            "secrets": catalog.secrets(),
            "ssc-start": catalog.app("ssc", "start"),
            "ssc-stop": catalog.app("ssc", "stop"),
            "ssc-destroy": catalog.app("ssc", "destroy"),
        }
        execution = OperationRunner().run(operations[args.operation], execute=args.execute)
        print(f"Operation: {execution.operation_id}")
        print(f"Command: {' '.join(execution.command)}")
        print(f"Executed: {str(execution.executed).lower()}")
        print(execution.detail)
        return 0 if execution.ok else 1
    if args.command == "logs" and args.pod:
        execution = OperationRunner().run(OperationCatalog().logs(args.pod, follow=args.follow))
        print(f"Command: {' '.join(execution.command)}")
        print(execution.detail)
        return 0 if execution.ok else 1
    if args.command == "runbook" and args.preview:
        execution = OperationRunner().run(OperationCatalog().runbook(args.preview))
        print(f"Command: {' '.join(execution.command)}")
        print(execution.detail)
        return 0 if execution.ok else 1
    if args.command == "deploy" and args.plan:
        profile = build_profile(args.plan)
        adapter = BashOperationAdapter()
        step_ids = tuple(
            step.step_id for step in profile.steps
            if step.step_id in adapter_step_ids()
        )
        plan = adapter.build_plan(profile.label, step_ids)
        print(f"Deployment plan: {plan.name}")
        for index, step in enumerate(plan.steps, start=1):
            deps = ", ".join(step.dependencies) if step.dependencies else "none"
            print(f"{index}. {step.step_id}: {' '.join(step.command)} (depends on: {deps})")
        return 0
    if args.command == "web" and args.check:
        config = WebConsoleConfig(bind_host=args.bind, allow_lan=args.allow_lan, access_token=args.token)
        issues = config.validate()
        if issues:
            for issue in issues:
                print(issue)
            return 1
        status, body = WebConsoleApp(config).api_response("/api/status")
        print(f"web console check: {status}")
        print(f"operations: {len(body['operations'])}")
        return 0
    if args.command == "tui" and args.demo_screen:
        print(render_guided_step(build_demo_snapshot()), end="")
        return 0
    print(args.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
