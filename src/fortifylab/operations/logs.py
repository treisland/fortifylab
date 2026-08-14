"""Pod log selection helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LogSelectionDecision:
    decision: str
    pods: tuple[str, ...]

    def shell_lines(self) -> tuple[str, ...]:
        selected = self.pods[0] if self.decision == "single" and self.pods else ""
        return (f"decision={self.decision}", f"pod={selected}", f"count={len(self.pods)}")


def matching_pods(pods: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    return tuple(pod for pod in pods if pod.startswith(prefix))


def should_skip_selection(pods: tuple[str, ...], prefix: str) -> bool:
    return len(matching_pods(pods, prefix)) == 1


def log_selection_decision(pods: tuple[str, ...], prefix: str) -> LogSelectionDecision:
    matches = matching_pods(pods, prefix)
    if not matches:
        return LogSelectionDecision("none", matches)
    if len(matches) == 1:
        return LogSelectionDecision("single", matches)
    return LogSelectionDecision("multiple", matches)
