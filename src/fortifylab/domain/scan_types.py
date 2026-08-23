"""Scan-type strategy model for the first-scan one-click demo.

``scripts/wizard/scan-demo.sh`` already documents its own extension point in
a header comment: every scan type implements a fixed set of
``scan_type_<verb>_<type>`` Bash functions (prereqs, login, sensor_check,
rulepack_check, setup_appversion, acquire, package, submit, poll, verify,
results, logout), and ``scan_demo_run`` dispatches through that shape by
name. That is a Strategy pattern in everything but syntax, so this module
gives it an explicit Python shape: a ``ScanType`` protocol plus one step per
verb, described declaratively as ``ScanStep`` data (label, fcli command
shape) rather than executed here.

This module is descriptive, not executable: it models what a scan type
*is* (its ordered steps, what each one is for) so the TUI can preview or
render progress, mirroring "Show the exact fcli command sequence before
running the demo" from the Bash flow. Wiring these steps to a live
``OperationRunner`` execution is M3 (deploy service), not this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ScanStep:
    """One stage of a scan-type's run, matching one ``scan_type_<verb>_<type>``
    Bash function."""

    verb: str
    label: str
    command_template: tuple[str, ...] = field(default_factory=tuple)


class ScanType(Protocol):
    """A first-scan demo strategy: a named, ordered sequence of steps."""

    scan_type_id: str
    display_name: str

    def steps(self) -> tuple[ScanStep, ...]:
        """Ordered steps this scan type runs, prereqs through logout."""
        ...


@dataclass(frozen=True)
class SastIwaJavaScan:
    """The only scan type implemented today: SAST against IWA-Java via
    ScanCentral SAST, mirroring ``scan_type_*_sast_iwa_java`` in
    ``scan-demo.sh``."""

    scan_type_id: str = "sast_iwa_java"
    display_name: str = "SAST · IWA-Java"

    def steps(self) -> tuple[ScanStep, ...]:
        return (
            ScanStep("prereqs", "Check fcli, SSC_URL, git, and Maven are available"),
            ScanStep("check_egress", "Confirm the IWA-Java repository is reachable"),
            ScanStep(
                "login",
                "Log into SSC with fcli, reusing an existing session when possible",
                ("fcli", "ssc", "session", "login", "--url", "{ssc_url}", "--session", "{session_name}"),
            ),
            ScanStep("sensor_check", "Confirm a ScanCentral SAST sensor is available"),
            ScanStep("rulepack_check", "Fail closed if required rulepacks are missing"),
            ScanStep(
                "setup_appversion",
                "Create the demo's SSC application version if it does not exist yet",
                ("fcli", "ssc", "appversion", "create", "{app}:{release}", "--skip-if-exists"),
            ),
            ScanStep("acquire", "Clone the IWA-Java repository"),
            ScanStep(
                "package",
                "Package the source with ScanCentral SAST via Maven",
                ("fcli", "sc-sast", "scan", "package", "-bt", "mvn", "-o", "{package_path}"),
            ),
            ScanStep(
                "submit",
                "Submit the packaged scan to ScanCentral SAST",
                ("fcli", "sc-sast", "scan", "start", "--package", "{package_path}", "--appversion", "{app}:{release}"),
            ),
            ScanStep("poll", "Poll scan status until it completes or times out"),
            ScanStep("verify", "Confirm the scan artifact published to SSC"),
            ScanStep("results", "Summarize severity counts and link to the SSC application version"),
            ScanStep("logout", "Log out the fcli SSC session"),
        )
