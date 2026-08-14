"""Guided deployment profile data mirrored from the Bash wizard."""

from __future__ import annotations

from dataclasses import dataclass

from .guided import GuidedStep


PLATFORM_STEPS = ("prereqs", "inputs", "preflight", "certs", "dashboard", "secrets")
DATA_STEPS = ("mysql", "postgresql")
FINAL_STEPS = ("configure",)

PROFILE_COMPONENTS: dict[str, tuple[str, ...]] = {
    "ssc_only": ("ssc",),
    "sast_standalone": ("sast_controller",),
    "sast_full": ("ssc", "sast_controller", "sast_sensor"),
    "dast_full": ("ssc", "lim", "dast_core", "dast_scanner"),
    "full_lab": ("ssc", "lim", "sast_controller", "sast_sensor", "dast_core", "dast_scanner"),
    "sample_apps": ("sample_juice_shop", "sample_webgoat", "sample_dvwa"),
}

PROFILE_LABELS: dict[str, str] = {
    "ssc_only": "SSC only",
    "sast_standalone": "SAST standalone",
    "sast_full": "SAST full with SSC",
    "dast_full": "DAST full",
    "full_lab": "Full lab",
    "sample_apps": "Sample vulnerable apps",
    "custom": "Custom",
}

STEP_LABELS: dict[str, str] = {
    "prereqs": "Install prerequisites",
    "inputs": "Collect deployment inputs",
    "preflight": "Deployment pre-flight",
    "certs": "Generate TLS certificates",
    "dashboard": "Deploy Kubernetes Dashboard",
    "secrets": "Create Kubernetes Secrets",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "ssc": "Software Security Center",
    "lim": "License and Infrastructure Manager",
    "sast_controller": "ScanCentral SAST controller",
    "sast_sensor": "ScanCentral SAST sensor",
    "dast_core": "ScanCentral DAST Core",
    "dast_scanner": "ScanCentral DAST scanner",
    "sample_juice_shop": "OWASP Juice Shop",
    "sample_webgoat": "OWASP WebGoat",
    "sample_dvwa": "Damn Vulnerable Web Application",
    "configure": "Post-deployment configuration",
}

LOG_SCOPES: dict[str, str] = {
    "mysql": "mysql*",
    "postgresql": "postgresql*",
    "ssc": "ssc-webapp*",
    "lim": "lim*",
    "sast_controller": "scancentral-sast-controller*",
    "sast_sensor": "scancentral-sast*",
    "dast_core": "sdast-core*",
    "dast_scanner": "sdast*",
    "sample_juice_shop": "sample-juice-shop*",
    "sample_webgoat": "sample-webgoat*",
    "sample_dvwa": "sample-dvwa*",
}


@dataclass(frozen=True)
class DeploymentProfile:
    """Selected guided deployment profile and expanded step plan."""

    profile_id: str
    label: str
    components: tuple[str, ...]
    steps: tuple[GuidedStep, ...]


def profile_components_for(profile_id: str) -> tuple[str, ...]:
    return PROFILE_COMPONENTS.get(profile_id, PROFILE_COMPONENTS["full_lab"])


def expand_components(components: tuple[str, ...]) -> tuple[str, ...]:
    expanded = list(components)
    if "ssc" in expanded and "mysql" not in expanded:
        expanded.insert(0, "mysql")
    if any(component in expanded for component in ("lim", "dast_core", "dast_scanner")):
        for required in ("postgresql", "lim"):
            if required not in expanded:
                expanded.insert(0, required)
        if "ssc" not in expanded:
            expanded.insert(0, "ssc")
    if "sast_sensor" in expanded and "sast_controller" not in expanded:
        expanded.insert(0, "sast_controller")
    return tuple(dict.fromkeys((*PLATFORM_STEPS, *expanded, *FINAL_STEPS)))


def build_profile(profile_id: str = "full_lab", custom_components: tuple[str, ...] | None = None) -> DeploymentProfile:
    components = custom_components if profile_id == "custom" and custom_components is not None else profile_components_for(profile_id)
    steps = tuple(
        GuidedStep(
            step_id=step_id,
            label=STEP_LABELS[step_id],
            help_text=f"Prototype guided step for {STEP_LABELS[step_id]}.",
            optional=step_id.startswith("sample_") or step_id == "configure",
            manual=step_id in ("inputs", "configure"),
            log_scope=LOG_SCOPES.get(step_id),
        )
        for step_id in expand_components(components)
    )
    return DeploymentProfile(
        profile_id=profile_id,
        label=PROFILE_LABELS.get(profile_id, PROFILE_LABELS["full_lab"]),
        components=components,
        steps=steps,
    )
