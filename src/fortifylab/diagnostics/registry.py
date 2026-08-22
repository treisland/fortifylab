"""Registry and image pull diagnostics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImagePullFinding:
    resource: str
    reason: str
    message: str


def image_pull_findings(events: tuple[str, ...]) -> tuple[ImagePullFinding, ...]:
    findings: list[ImagePullFinding] = []
    for line in events:
        if "ImagePullBackOff" in line or "ErrImagePull" in line or "Back-off pulling image" in line:
            parts = line.split()
            resource = next((part for part in parts if "/" in part), "<unknown>")
            reason = next((part for part in parts if "Pull" in part or "BackOff" in part), "ImagePull")
            findings.append(
                ImagePullFinding(
                    resource=resource,
                    reason=reason,
                    message="Image pull failed or is backing off; refresh registry credentials and confirm image access.",
                )
            )
    return tuple(findings)


def docker_auth_findings(config_text: str | None) -> tuple[str, ...]:
    if not config_text or '"auths"' not in config_text:
        return ("Docker auth config is missing; image pull secrets may be stale.",)
    return ()


def regcred_findings(secret_type: str | None) -> tuple[str, ...]:
    if secret_type != "kubernetes.io/dockerconfigjson":
        return ("regcred is missing or is not a dockerconfigjson image pull secret.",)
    return ()
