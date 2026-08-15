"""Read-only Kubernetes polling for live deployment status."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from fortifylab.config import parse_env_text, validate_hosts_and_urls
from fortifylab.core.command import CommandResult, run_command
from fortifylab.tui.profiles import LOG_SCOPES, build_profile

from .hints import hints_for_step
from .model import EventSummary, HelmReleaseSummary, LiveDeploymentSnapshot, LiveState, LiveStepStatus, PodSummary, RouteSummary


Runner = Callable[[tuple[str, ...]], CommandResult]

PLATFORM_STEP_IDS = {"prereqs", "inputs", "preflight", "certs", "dashboard", "secrets"}
REQUIRED_SECRET_NAMES = {
    "regcred",
    "fortify-secrets",
    "tls",
    "tls-pfx",
    "tls-pfx-password",
    "scdast-utilityservice-certificate",
    "scdast-db-owner",
    "scdast-db-standard",
    "scdast-ssc-serviceaccount",
    "scdast-service-token",
    "lim-pool",
    "lim-admin-credentials",
    "lim-jwt-security-key",
    "lim-server-certificate",
    "lim-signing-certificate",
    "lim-signing-certificate-password",
}
REQUIRED_FORTIFY_SECRET_KEYS = {
    "fortify.license",
    "ssc.autoconfig",
    "secret.key",
    "keystore.jks",
    "truststore",
    "default_password",
    "scancentral-client-auth-token",
    "scancentral-worker-auth-token",
    "scancentral-ssc-scancentral-ctrl-secret",
    "jvm_truststore",
    "http_truststore",
    "keystore_password",
    "key_password",
    "jvm_truststore_password",
    "http_truststore_password",
    "keystore_alias",
}


class LiveStatusPoller:
    def __init__(
        self,
        *,
        namespace: str = "fortify",
        profile: str = "full_lab",
        kubectl: str = "microk8s kubectl",
        helm: str = "microk8s helm3",
        env_file: Path | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.namespace = namespace
        self.profile = profile
        self.env_file = env_file
        self.kubectl = tuple(kubectl.split())
        self.helm = tuple(helm.split())
        self.runner = runner or self._default_runner

    def snapshot(self) -> LiveDeploymentSnapshot:
        warnings: list[str] = []
        pods_json = self._json_command((*self.kubectl, "-n", self.namespace, "get", "pods", "-o", "json"), warnings)
        events_json = self._json_command((*self.kubectl, "-n", self.namespace, "get", "events", "-o", "json", "--sort-by=.lastTimestamp"), warnings)
        ingress_json = self._json_command((*self.kubectl, "-n", self.namespace, "get", "ingress", "-o", "json"), warnings)
        endpoints_json = self._json_command((*self.kubectl, "-n", self.namespace, "get", "endpoints", "-o", "json"), warnings)
        helm_json = self._json_command((*self.helm, "-n", self.namespace, "list", "-o", "json"), warnings)
        secrets_json = self._json_command((*self.kubectl, "-n", self.namespace, "get", "secrets", "-o", "json"), warnings)

        pods = _parse_pods(pods_json)
        events = _parse_events(events_json)
        routes = _parse_routes(ingress_json, endpoints_json)
        releases = _parse_helm(helm_json)
        env_path, env_values, env_issues = self._env_state()
        profile_id = env_values.get("FORTIFY_DEPLOYMENT_PROFILE") or self.profile
        profile = build_profile(profile_id)
        platform = PlatformState(self, env_path, env_values, env_issues, secrets_json)
        steps = tuple(self._step_status(step.step_id, step.label, pods, events, routes, platform) for step in profile.steps)
        overall = _overall_state(steps, warnings)
        return LiveDeploymentSnapshot(
            namespace=self.namespace,
            profile=profile.profile_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            overall_state=overall,
            steps=steps,
            helm_releases=releases,
            tool_warnings=tuple(dict.fromkeys(warnings)),
        )

    def _json_command(self, command: tuple[str, ...], warnings: list[str]) -> object:
        result = self.runner(command)
        if not result.ok:
            warnings.append(f"Command failed: {' '.join(command)}")
            return {}
        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            warnings.append(f"Command returned invalid JSON: {' '.join(command)}")
            return {}

    def _step_status(
        self,
        step_id: str,
        label: str,
        pods: tuple[PodSummary, ...],
        events: tuple[EventSummary, ...],
        routes: tuple[RouteSummary, ...],
        platform: "PlatformState",
    ) -> LiveStepStatus:
        scope = LOG_SCOPES.get(step_id)
        step_pods = _matching_pods(scope, pods)
        step_events = _matching_events(step_pods, events)
        step_routes = _matching_routes(step_id, routes)
        hints = hints_for_step(step_id, step_pods, step_events, step_routes)
        state = _state_for(step_pods, hints)
        detail = _detail_for(state, step_pods, hints)
        platform_state = platform.state_for(step_id)
        if platform_state is not None and (state is LiveState.PENDING or step_id in PLATFORM_STEP_IDS):
            state, detail = platform_state
        return LiveStepStatus(step_id=step_id, label=label, state=state, detail=detail, pods=step_pods, events=step_events, routes=step_routes, hints=hints)

    def _env_state(self) -> tuple[Path, dict[str, str], tuple[str, ...]]:
        env_path = Path(self.env_file) if self.env_file else Path.cwd() / ".env"
        if not env_path.is_file():
            return env_path, {}, ("No .env file found.",)
        document = parse_env_text(env_path.read_text(encoding="utf-8"))
        return env_path, document.values(), validate_hosts_and_urls(document)

    @staticmethod
    def _default_runner(command: tuple[str, ...]) -> CommandResult:
        try:
            return run_command(command, timeout=20)
        except OSError as exc:
            return CommandResult(args=command, returncode=127, stdout="", stderr=str(exc), duration_seconds=0)


class PlatformState:
    def __init__(self, poller: LiveStatusPoller, env_path: Path, env_values: dict[str, str], env_issues: tuple[str, ...], secrets_payload: object) -> None:
        self.poller = poller
        self.env_path = env_path
        self.env_values = env_values
        self.env_issues = env_issues
        self.secrets = _secret_items(secrets_payload)

    def state_for(self, step_id: str) -> tuple[LiveState, str] | None:
        if step_id == "prereqs":
            return self._prereqs()
        if step_id == "inputs":
            return self._inputs()
        if step_id == "preflight":
            return self._preflight()
        if step_id == "certs":
            return self._certs()
        if step_id == "dashboard":
            return self._dashboard()
        if step_id == "secrets":
            return self._secrets()
        return None

    def _prereqs(self) -> tuple[LiveState, str]:
        required = ("openssl", "envsubst", "curl", "java", "docker", "mkcert", "microk8s")
        missing = [command for command in required if shutil.which(command) is None]
        if missing:
            return LiveState.PENDING, f"Missing host tools: {', '.join(missing)}."
        return LiveState.COMPLETE, "Host prerequisite commands are available."

    def _inputs(self) -> tuple[LiveState, str]:
        if not self.env_path.is_file():
            return LiveState.PENDING, f"No .env file found at {self.env_path}."
        if self.env_issues:
            return LiveState.BLOCKED, self.env_issues[0]
        return LiveState.COMPLETE, ".env host and URL values are usable."

    def _preflight(self) -> tuple[LiveState, str]:
        prereqs, _ = self._prereqs()
        inputs, detail = self._inputs()
        if prereqs is not LiveState.COMPLETE:
            return LiveState.PENDING, "Waiting for host prerequisites before pre-flight."
        if inputs is not LiveState.COMPLETE:
            return inputs, detail
        storage = self.poller.runner((*self.poller.kubectl, "get", "storageclass", "nfs", "-o", "json"))
        docker_config = Path.home() / ".docker" / "config.json"
        if not storage.ok:
            return LiveState.PENDING, "StorageClass nfs is not available yet."
        if not docker_config.is_file():
            return LiveState.PENDING, "Docker auth config is not available yet."
        return LiveState.COMPLETE, "Pre-flight prerequisites are present."

    def _certs(self) -> tuple[LiveState, str]:
        root = self.env_path.parent
        certs_dir = Path(self.env_values.get("FORTIFY_CERTS") or root / "certs")
        paths = {
            "TLS certificate": Path(self.env_values.get("SERVER_CERT") or certs_dir / "tls.crt"),
            "TLS key": Path(self.env_values.get("SERVER_KEY") or certs_dir / "tls.key"),
            "JVM keystore": Path(self.env_values.get("JVM_KEYSTORE") or certs_dir / "keystore.jks"),
            "Truststore": Path(self.env_values.get("TRUSTSTORE") or certs_dir / "truststore"),
        }
        missing = [label for label, item in paths.items() if not item.is_file() or item.stat().st_size == 0]
        if missing:
            return LiveState.PENDING, f"Missing certificate artifacts: {', '.join(missing)}."
        return LiveState.COMPLETE, "TLS certificate, key, keystore, and truststore artifacts exist."

    def _dashboard(self) -> tuple[LiveState, str]:
        dashboard_ns = "kubernetes-dashboard"
        kong = self.poller.runner((*self.poller.kubectl, "-n", dashboard_ns, "get", "service", "kubernetes-dashboard-kong-proxy", "-o", "json"))
        if not kong.ok:
            dashboard_ns = "kube-system"
        ingress = self.poller.runner((*self.poller.kubectl, "-n", dashboard_ns, "get", "ingress", "ingress-dashboard", "-o", "json"))
        if not ingress.ok:
            return LiveState.PENDING, "Dashboard ingress is not present yet."
        return LiveState.COMPLETE, "Dashboard ingress is present."

    def _secrets(self) -> tuple[LiveState, str]:
        names = set(self.secrets)
        missing_names = sorted(REQUIRED_SECRET_NAMES - names)
        if missing_names:
            return LiveState.PENDING, f"Missing Kubernetes Secret {missing_names[0]}."
        fortify = self.secrets.get("fortify-secrets", set())
        missing_keys = sorted(REQUIRED_FORTIFY_SECRET_KEYS - set(fortify))
        if missing_keys:
            return LiveState.PENDING, f"Missing key {missing_keys[0]} in secret fortify-secrets."
        return LiveState.COMPLETE, "All required Kubernetes Secrets and fortify-secrets keys are present."


def _secret_items(payload: object) -> dict[str, set[str]]:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    result: dict[str, set[str]] = {}
    for item in items:
        name = item.get("metadata", {}).get("name", "")
        data = item.get("data", {}) if isinstance(item.get("data"), dict) else {}
        if name:
            result[name] = set(data)
    return result


def _parse_pods(payload: object) -> tuple[PodSummary, ...]:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    pods: list[PodSummary] = []
    for item in items:
        metadata = item.get("metadata", {})
        status = item.get("status", {})
        statuses = status.get("containerStatuses", []) or []
        ready = sum(1 for container in statuses if container.get("ready"))
        total = len(statuses)
        reason = status.get("reason") or _container_waiting_reason(statuses)
        restarts = sum(int(container.get("restartCount", 0)) for container in statuses)
        pods.append(PodSummary(name=metadata.get("name", "unknown"), ready=ready, total=total, phase=status.get("phase", "Unknown"), reason=reason, restarts=restarts))
    return tuple(pods)


def _container_waiting_reason(statuses: list[dict]) -> str | None:
    for status in statuses:
        waiting = (status.get("state") or {}).get("waiting")
        if waiting and waiting.get("reason"):
            return waiting["reason"]
    return None


def _parse_events(payload: object) -> tuple[EventSummary, ...]:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    events: list[EventSummary] = []
    for item in items[-12:]:
        involved = item.get("involvedObject", {})
        events.append(
            EventSummary(
                type=item.get("type", ""),
                reason=item.get("reason", ""),
                object=f"{involved.get('kind', '').lower()}/{involved.get('name', '')}".strip("/"),
                message=item.get("message", ""),
                age=item.get("lastTimestamp") or item.get("eventTime") or item.get("metadata", {}).get("creationTimestamp"),
            )
        )
    return tuple(events)


def _parse_routes(ingress_payload: object, endpoints_payload: object) -> tuple[RouteSummary, ...]:
    endpoint_names = _ready_endpoint_names(endpoints_payload)
    items = ingress_payload.get("items", []) if isinstance(ingress_payload, dict) else []
    routes: list[RouteSummary] = []
    for item in items:
        spec = item.get("spec", {})
        tls_by_host = {host: tls.get("secretName") for tls in spec.get("tls", []) for host in tls.get("hosts", [])}
        for rule in spec.get("rules", []):
            host = rule.get("host", "")
            paths = ((rule.get("http") or {}).get("paths") or [])
            service = None
            if paths:
                service = (((paths[0].get("backend") or {}).get("service") or {}).get("name"))
            routes.append(RouteSummary(host=host, ingress_present=True, tls_secret=tls_by_host.get(host), service_name=service, endpoints_ready=bool(service and service in endpoint_names)))
    return tuple(routes)


def _ready_endpoint_names(payload: object) -> set[str]:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    names: set[str] = set()
    for item in items:
        if item.get("subsets"):
            names.add(item.get("metadata", {}).get("name", ""))
    return names


def _parse_helm(payload: object) -> tuple[HelmReleaseSummary, ...]:
    items = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
    releases = []
    for item in items:
        releases.append(HelmReleaseSummary(name=item.get("name", ""), status=item.get("status", ""), chart=item.get("chart"), revision=str(item.get("revision")) if item.get("revision") is not None else None))
    return tuple(releases)


def _matching_pods(scope: str | None, pods: tuple[PodSummary, ...]) -> tuple[PodSummary, ...]:
    if not scope:
        return ()
    prefix = scope.rstrip("*")
    return tuple(pod for pod in pods if pod.name.startswith(prefix))


def _matching_events(pods: tuple[PodSummary, ...], events: tuple[EventSummary, ...]) -> tuple[EventSummary, ...]:
    names = {pod.name for pod in pods}
    return tuple(event for event in events if any(name in event.object or name in event.message for name in names))


def _matching_routes(step_id: str, routes: tuple[RouteSummary, ...]) -> tuple[RouteSummary, ...]:
    needles = {
        "ssc": "ssc.",
        "lim": "lim.",
        "sast_controller": "sast.",
        "dast_core": "dast.",
        "dast_scanner": "dast.",
    }
    needle = needles.get(step_id)
    if not needle:
        return ()
    return tuple(route for route in routes if route.host.startswith(needle))


def _state_for(pods: tuple[PodSummary, ...], hints: tuple) -> LiveState:
    if any(getattr(hint, "severity", None) and hint.severity.value == "blocked" for hint in hints):
        return LiveState.BLOCKED
    if not pods:
        return LiveState.PENDING
    if all(pod.total > 0 and pod.ready == pod.total and pod.phase == "Running" for pod in pods):
        return LiveState.COMPLETE
    if any(pod.phase == "Failed" for pod in pods):
        return LiveState.FAILED
    return LiveState.IN_PROGRESS


def _detail_for(state: LiveState, pods: tuple[PodSummary, ...], hints: tuple) -> str:
    if hints:
        return hints[0].message
    if state is LiveState.PENDING:
        return "No matching pod status applies to this step yet."
    if state is LiveState.COMPLETE:
        return "All matching pods report ready."
    return "Waiting for matching pods, routes, or endpoints to become ready."


def _overall_state(steps: tuple[LiveStepStatus, ...], warnings: list[str]) -> LiveState:
    if warnings:
        return LiveState.UNKNOWN
    states = {step.state for step in steps if step.pods or step.routes or step.step_id in PLATFORM_STEP_IDS}
    if not states:
        return LiveState.PENDING
    if LiveState.BLOCKED in states:
        return LiveState.BLOCKED
    if LiveState.FAILED in states:
        return LiveState.FAILED
    if all(state is LiveState.COMPLETE for state in states):
        return LiveState.COMPLETE
    return LiveState.IN_PROGRESS
