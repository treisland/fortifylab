"""Lab status dashboard -- the interactive replacement for
``setup_readiness_items()`` / ``setup_readiness_score()`` in
``scripts/wizard/setup.sh``.

Entirely read-only: every check here either reads a local file's
existence/non-emptiness, reads a value already present in the current
``.env``, or makes a read-only ``kubectl get``/``cluster-info`` call. None
of them open, decode, or cryptographically validate the *contents* of a
TLS private key, license file, or Kubernetes Secret -- existence and
non-emptiness are the only signals used, the same posture as every other
status/summary screen in this migration.

Scope trim, deliberate: Bash's ``certs_ready()`` goes one step further
than this and actually runs ``openssl rsa -check`` / ``keytool -list``
against the private key and JVM keystore, passing the keystore password
(``$DEFAULT_PASS``) on the command line to validate the material itself.
That is not ported here -- a password on a subprocess argv is visible to
anything reading ``/proc`` or ``ps`` on the host, and "the material is
cryptographically valid" is a materially larger claim than "the files
exist and are not empty." This service only checks the latter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import tomllib

from fortifylab.config.repair import validate_hosts_and_urls
from fortifylab.config.store import ConfigStore
from fortifylab.domain.flight_plans import default_catalog_path, merged_read_catalog

from .kubectl_base import KubectlBackedService, KubectlRunner

__all__ = ["KubectlRunner", "LabStatusService", "ReadinessCheck"]


@dataclass(frozen=True)
class ReadinessCheck:
    label: str
    ready: bool
    detail: str = ""


def _nonempty_file(path_str: str) -> bool:
    if not path_str:
        return False
    path = Path(path_str)
    return path.is_file() and path.stat().st_size > 0


@dataclass
class LabStatusService(KubectlBackedService):
    env_file: Path = field(default_factory=lambda: Path(".env"))
    catalog_path: Path = field(default_factory=default_catalog_path)
    repo_root: Path = field(default_factory=lambda: Path("."))
    namespace: str = "fortify"
    docker_config_path: Path = field(default_factory=lambda: Path.home() / ".docker" / "config.json")

    def _env_values(self) -> dict[str, str]:
        if not self.env_file.exists():
            return {}
        return ConfigStore(self.env_file).load().values()

    def env_file_exists(self) -> bool:
        return _nonempty_file(str(self.env_file))

    def hosts_and_urls_valid(self) -> bool:
        if not self.env_file.exists():
            return False
        document = ConfigStore(self.env_file).load()
        return not validate_hosts_and_urls(document)

    def deployment_profile(self) -> str:
        return self._env_values().get("FORTIFY_DEPLOYMENT_PROFILE", "")

    def profile_selected(self) -> bool:
        return bool(self.deployment_profile())

    def flight_plan_id(self) -> str:
        return self._env_values().get("FORTIFY_FLIGHT_PLAN", "")

    def flight_plan_ready(self) -> bool:
        plan_id = self.flight_plan_id()
        if not plan_id:
            return False
        try:
            catalog = merged_read_catalog(self.catalog_path)
        except (OSError, tomllib.TOMLDecodeError):
            return False
        return plan_id in catalog.flight_plans

    def license_ready(self) -> bool:
        return _nonempty_file(self._env_values().get("FORTIFY_LICENSE_FILE", ""))

    def docker_auth_ready(self) -> bool:
        return shutil.which("docker") is not None and _nonempty_file(str(self.docker_config_path))

    def regcred_exists(self) -> bool:
        return self._run(("-n", self.namespace, "get", "secret", "regcred")).ok

    def tls_artifacts_exist(self) -> bool:
        values = self._env_values()
        return all(_nonempty_file(values.get(key, "")) for key in ("SERVER_CERT", "SERVER_KEY", "JVM_KEYSTORE", "TRUSTSTORE"))

    def root_ca_exported(self) -> bool:
        # Bash's setup_root_ca_exported() checks a fixed path,
        # $FORTIFY_HOME_K8S/certs/rootCA.pem -- not $ROOTCA_CERT, which
        # can point elsewhere (or be unset) without affecting what Bash
        # actually checks. Match that fixed path rather than reading
        # ROOTCA_CERT from .env, which was checking the wrong source.
        return _nonempty_file(str(self.repo_root / "certs" / "rootCA.pem"))

    def fcli_truststore_available(self) -> bool:
        # Bash's setup_fcli_trust_ready() checks, in order: the live
        # FCLI_TRUSTSTORE env var (set by a shell that has sourced fcli
        # trust config), then .env's TRUSTSTORE, then a fixed fallback
        # path. The FCLI_TRUSTSTORE-vs-fcli_trust_configured_current
        # cross-check (comparing it against TYPE/PWD too) needs sourcing
        # a shell profile, which doesn't translate to a single Python
        # process -- that part stays a deliberate scope trim -- but the
        # two straightforward fallbacks were missing entirely.
        live_truststore = os.environ.get("FCLI_TRUSTSTORE", "")
        if _nonempty_file(live_truststore):
            return True
        if _nonempty_file(self._env_values().get("TRUSTSTORE", "")):
            return True
        return _nonempty_file(str(self.repo_root / "certs" / "truststore"))

    def cluster_reachable(self) -> bool:
        return self._run(("cluster-info",)).ok

    def readiness(self) -> tuple[ReadinessCheck, ...]:
        return (
            ReadinessCheck(".env file exists", self.env_file_exists(), "copy .env.example first"),
            ReadinessCheck("Domain and URLs are valid", self.hosts_and_urls_valid(), "repair derived values from DOMAIN"),
            ReadinessCheck("Deployment profile selected", self.profile_selected(), "choose a profile"),
            ReadinessCheck("Fortify Flight Plan selected", self.flight_plan_ready(), "choose a curated plan or repair the catalog"),
            ReadinessCheck("Fortify license is readable", self.license_ready(), "add or point to fortify.license"),
            ReadinessCheck("Docker registry auth is usable", self.docker_auth_ready(), "run Docker login or refresh credentials"),
            ReadinessCheck("Kubernetes image pull secret exists", self.regcred_exists(), "refresh regcred after cluster is ready"),
            ReadinessCheck("Lab TLS artifacts exist", self.tls_artifacts_exist(), "generate TLS certificates"),
            ReadinessCheck("Public mkcert root CA exported", self.root_ca_exported(), "export certs/rootCA.pem for client trust"),
            ReadinessCheck("fcli truststore is available", self.fcli_truststore_available(), "configure fcli lab trust"),
            ReadinessCheck("Kubernetes cluster is reachable", self.cluster_reachable(), "start MicroK8s or check kube context"),
        )

    def score(self) -> tuple[int, int]:
        checks = self.readiness()
        return sum(1 for check in checks if check.ready), len(checks)
