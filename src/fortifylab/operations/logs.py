"""Pod log selection helpers."""

from __future__ import annotations


def matching_pods(pods: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    return tuple(pod for pod in pods if pod.startswith(prefix))


def should_skip_selection(pods: tuple[str, ...], prefix: str) -> bool:
    return len(matching_pods(pods, prefix)) == 1
