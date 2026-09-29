"""Contracts for the Jenkins CI integration: lab TLS and domain, agents that
trust the lab root CA, fcli on agents, and the Integrations menu."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path

# Never let sourced wizard code query a real cluster for deployed versions.
os.environ.setdefault("FORTIFY_DEPLOYED_VERSIONS", "off")

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/jenkins"
INIT = APP / "agent-init.sh"
WIZARD = ROOT / "start_wizard.sh"

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional
    yaml = None

HAVE_CERT_TOOLS = all(shutil.which(tool) for tool in ("openssl", "keytool", "envsubst"))


def make_ca(directory: Path, name: str, sans: str | None = None) -> tuple[Path, Path]:
    """Self-signed certificate (a CA, or a leaf when sans is given)."""
    key = directory / f"{name}.key"
    cert = directory / f"{name}.pem"
    command = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
               "-subj", f"/CN={name}", "-keyout", str(key), "-out", str(cert)]
    if sans:
        command += ["-addext", f"subjectAltName={sans}"]
    subprocess.run(command, check=True, capture_output=True)
    return cert, key


def fake_fcli_release(directory: Path, version: str, corrupt_checksum: bool = False) -> None:
    """A fcli-linux.tgz whose `fcli` records truststore configuration."""
    script = textwrap.dedent("""\
        #!/bin/sh
        if [ "$1" = --version ]; then echo "fcli version FAKE"; exit 0; fi
        if [ "$1 $2 $3" = "config truststore set" ]; then
            mkdir -p "$FCLI_DATA_DIR" && printf '%s\\n' "$*" >"$FCLI_DATA_DIR/truststore-args"
        fi
    """).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("fcli")
        info.size = len(script)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(script))
    release = directory / f"v{version}"
    release.mkdir(parents=True)
    data = buffer.getvalue()
    (release / "fcli-linux.tgz").write_bytes(data)
    digest = "0" * 64 if corrupt_checksum else hashlib.sha256(data).hexdigest()
    (release / "fcli-linux.tgz.sha256").write_text(f"{digest}  fcli-linux.tgz\n", encoding="utf-8")


def fake_maven_release(directory: Path, version: str, corrupt_checksum: bool = False) -> None:
    """An apache-maven-<version>-bin.tar.gz laid out like Maven Central's."""
    script = b"#!/bin/sh\necho \"Apache Maven FAKE\"\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in (f"apache-maven-{version}", f"apache-maven-{version}/bin"):
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            archive.addfile(info)
        info = tarfile.TarInfo(f"apache-maven-{version}/bin/mvn")
        info.size = len(script)
        info.mode = 0o644  # the installer must make it executable
        archive.addfile(info, io.BytesIO(script))
    release = directory / "maven" / version
    release.mkdir(parents=True)
    data = buffer.getvalue()
    (release / f"apache-maven-{version}-bin.tar.gz").write_bytes(data)
    digest = "0" * 128 if corrupt_checksum else hashlib.sha512(data).hexdigest()
    # Maven Central checksum files hold only the hash.
    (release / f"apache-maven-{version}-bin.tar.gz.sha512").write_text(digest, encoding="utf-8")


def java_cacerts() -> Path:
    keytool = Path(shutil.which("keytool") or "").resolve()
    return keytool.parent.parent / "lib/security/cacerts"


@unittest.skipUnless(HAVE_CERT_TOOLS, "openssl, keytool, and envsubst are required")
class AgentInitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ca, _ = make_ca(self.dir, "fortifylab-test-root")
        self.system_bundle = self.dir / "system-bundle.crt"
        make_ca(self.dir, "public-root")
        shutil.copy(self.dir / "public-root.pem", self.system_bundle)
        self.releases = self.dir / "releases"
        self.releases.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_init(self, ca: Path | None = None, **env: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update({
            "FORTIFYLAB_CA_FILE": str(ca or self.ca),
            "FORTIFYLAB_TRUST_DIR": str(self.dir / "trust"),
            "FORTIFYLAB_TOOLS_DIR": str(self.dir / "tools"),
            "FORTIFYLAB_JAVA_CACERTS": str(java_cacerts()),
            "FORTIFYLAB_SYSTEM_CA_BUNDLE": str(self.system_bundle),
            "FORTIFY_JENKINS_FCLI_VERSION": "9.9.9",
            "FCLI_RELEASE_BASE_URL": f"file://{self.releases}",
            "FORTIFY_JENKINS_MAVEN_VERSION": "",
            "MAVEN_RELEASE_BASE_URL": f"file://{self.releases}/maven",
        })
        environment.update(env)
        return subprocess.run(["bash", str(INIT)], check=False, capture_output=True, text=True, env=environment)

    def aliases(self) -> str:
        return subprocess.run(
            ["keytool", "-list", "-keystore", str(self.dir / "trust/cacerts"), "-storepass", "changeit"],
            check=True, capture_output=True, text=True,
        ).stdout

    def test_trust_bundle_keeps_public_cas_and_adds_lab_root(self) -> None:
        result = self.run_init(FORTIFY_JENKINS_FCLI_INSTALL="none")
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = self.aliases()
        self.assertIn("fortifylab-ca-1", listing)
        # The JDK's own public CAs are still present.
        default_count = subprocess.run(
            ["keytool", "-list", "-cacerts", "-storepass", "changeit"], check=True, capture_output=True, text=True,
        ).stdout.count("trustedCertEntry")
        self.assertEqual(listing.count("trustedCertEntry"), default_count + 1)
        bundle = (self.dir / "trust/ca-bundle.crt").read_text(encoding="utf-8")
        self.assertIn(self.system_bundle.read_text(encoding="utf-8").strip(), bundle)
        self.assertIn(self.ca.read_text(encoding="utf-8").strip(), bundle)
        self.assertFalse((self.dir / "tools").exists(), "none mode installs nothing")

    def test_every_certificate_in_a_ca_chain_is_imported(self) -> None:
        intermediate, _ = make_ca(self.dir, "intermediate")
        chain = self.dir / "chain.pem"
        chain.write_text(intermediate.read_text(encoding="utf-8") + self.ca.read_text(encoding="utf-8"), encoding="utf-8")
        self.run_init(ca=chain, FORTIFY_JENKINS_FCLI_INSTALL="none")
        listing = self.aliases()
        self.assertIn("fortifylab-ca-1", listing)
        self.assertIn("fortifylab-ca-2", listing)

    def test_auto_installs_verified_fcli_once_and_configures_its_trust(self) -> None:
        fake_fcli_release(self.releases, "9.9.9")
        first = self.run_init()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("installed fcli 9.9.9", first.stdout)
        link = self.dir / "tools/bin/fcli"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../fcli/9.9.9/fcli")
        args = (self.dir / "trust/fcli-data/truststore-args").read_text(encoding="utf-8")
        self.assertIn(f"--file {self.dir / 'trust/cacerts'} --type jks", args)
        second = self.run_init()
        self.assertIn("already on the tools volume", second.stdout)
        self.assertEqual(list((self.dir / "tools").glob(".fcli-install.*")), [])

    def test_maven_installs_verified_once_and_runs_through_path_link(self) -> None:
        fake_maven_release(self.releases, "3.9.99")
        first = self.run_init(FORTIFY_JENKINS_MAVEN_VERSION="3.9.99", FORTIFY_JENKINS_FCLI_INSTALL="manual")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("installed maven 3.9.99", first.stdout)
        link = self.dir / "tools/bin/mvn"
        self.assertEqual(os.readlink(link), "../maven/3.9.99/bin/mvn")
        run = subprocess.run([str(link)], check=True, capture_output=True, text=True)
        self.assertIn("Apache Maven FAKE", run.stdout)
        second = self.run_init(FORTIFY_JENKINS_MAVEN_VERSION="3.9.99", FORTIFY_JENKINS_FCLI_INSTALL="manual")
        self.assertIn("maven 3.9.99 already on the tools volume", second.stdout)

    def test_maven_checksum_mismatch_is_refused(self) -> None:
        fake_maven_release(self.releases, "3.9.99", corrupt_checksum=True)
        result = self.run_init(FORTIFY_JENKINS_MAVEN_VERSION="3.9.99", FORTIFY_JENKINS_FCLI_INSTALL="manual")
        self.assertEqual(result.returncode, 0)
        self.assertIn("maven 3.9.99 checksum mismatch", result.stderr)
        self.assertFalse((self.dir / "tools/bin/mvn").exists())

    def test_controller_mode_never_installs_maven(self) -> None:
        fake_maven_release(self.releases, "3.9.99")
        self.run_init(FORTIFY_JENKINS_MAVEN_VERSION="3.9.99", FORTIFY_JENKINS_FCLI_INSTALL="none")
        self.assertFalse((self.dir / "tools").exists())

    def test_bad_checksum_refuses_install_without_failing_the_pod(self) -> None:
        fake_fcli_release(self.releases, "9.9.9", corrupt_checksum=True)
        result = self.run_init()
        self.assertEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertFalse((self.dir / "tools/bin/fcli").exists())

    def test_download_failure_does_not_fail_the_pod(self) -> None:
        result = self.run_init()
        self.assertEqual(result.returncode, 0)
        self.assertIn("could not download fcli 9.9.9", result.stderr)

    def test_manual_mode_downloads_nothing_but_leaves_a_writable_bin(self) -> None:
        fake_fcli_release(self.releases, "9.9.9")
        result = self.run_init(FORTIFY_JENKINS_FCLI_INSTALL="manual")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.dir / "tools/bin").is_dir())
        self.assertFalse((self.dir / "tools/fcli").exists())
        self.assertIn("manual", result.stdout)

    def test_missing_ca_warns_and_still_succeeds(self) -> None:
        result = self.run_init(ca=self.dir / "absent.pem", FORTIFY_JENKINS_FCLI_INSTALL="none")
        self.assertEqual(result.returncode, 0)
        self.assertIn("lab root CA not found", result.stderr)


def render_values(**env: str) -> str:
    environment = os.environ.copy()
    environment.update({"FORTIFY_HOME_K8S": str(ROOT), "DOMAIN": "lab.example.test"})
    environment.update(env)
    return subprocess.run(
        ["bash", "-c", 'source "$FORTIFY_HOME_K8S/apps/jenkins/common.sh"; jenkins_apply_defaults; jenkins_render_values'],
        check=True, capture_output=True, text=True, env=environment,
    ).stdout


class ValuesTests(unittest.TestCase):
    def test_values_use_lab_tls_domain_and_admin_secret(self) -> None:
        text = render_values()
        self.assertNotRegex(text, r"\$\{(JENKINS|FORTIFY_JENKINS)")
        if yaml is None:
            self.skipTest("PyYAML not installed")
        values = yaml.safe_load(text)
        controller = values["controller"]
        ingress = controller["ingress"]
        self.assertEqual(ingress["hostName"], "jenkins.lab.example.test")
        self.assertEqual(ingress["ingressClassName"], "public")
        self.assertEqual(ingress["tls"], [{"secretName": "tls", "hosts": ["jenkins.lab.example.test"]}])
        self.assertEqual(ingress["annotations"]["traefik.ingress.kubernetes.io/router.tls"], "true")
        self.assertEqual(controller["jenkinsUrl"], "https://jenkins.lab.example.test/")
        self.assertEqual(controller["admin"]["existingSecret"], "jenkins-admin")
        self.assertFalse(controller["admin"]["createSecret"])
        self.assertIn("trustStore=/fortifylab-trust/cacerts", controller["javaOpts"])
        self.assertEqual(values["persistence"]["existingClaim"], "jenkins-home")

    def test_plugin_dir_is_emptied_before_the_chart_init_runs(self) -> None:
        # The chart's init runs `yes n | cp -i` under set -e; with coreutils
        # 9.x a declined overwrite exits 1, so an in-place restart with a
        # populated plugin-dir crash-loops unless it is emptied first.
        if yaml is None:
            self.skipTest("PyYAML not installed")
        init = yaml.safe_load(render_values())["controller"]["customInitContainers"]
        reset = {item["name"]: item for item in init}["fortifylab-plugin-dir-reset"]
        self.assertIn("rm -f /var/jenkins_plugins/*.jpi", " ".join(reset["command"]))
        self.assertEqual(reset["volumeMounts"], [{"name": "plugin-dir", "mountPath": "/var/jenkins_plugins"}])

    def test_agent_pod_template_trusts_lab_and_installs_fcli(self) -> None:
        if yaml is None:
            self.skipTest("PyYAML not installed")
        environment = {"FORTIFY_JENKINS_FCLI_VERSION": "3.23.3", "JENKINS_AGENT_MAX": "3"}
        os.environ.pop("FORTIFY_JENKINS_MAVEN_VERSION", None)
        values = yaml.safe_load(render_values(**environment))
        agent = values["agent"]
        self.assertEqual(agent["customJenkinsLabels"], ["fortifylab"])
        self.assertEqual(agent["containerCap"], 3)
        self.assertEqual(agent["yamlMergeStrategy"], "merge")
        pod = yaml.safe_load(agent["yamlTemplate"])["spec"]
        init = pod["initContainers"][0]
        self.assertEqual(init["image"], f"jenkins/inbound-agent:{agent['image']['tag']}")
        init_env = {item["name"]: item["value"] for item in init["env"]}
        self.assertEqual(init_env, {
            "FORTIFY_JENKINS_FCLI_INSTALL": "auto",
            "FORTIFY_JENKINS_FCLI_VERSION": "3.23.3",
            "FORTIFY_JENKINS_MAVEN_VERSION": "3.9.16",
        })
        jnlp = pod["containers"][0]
        self.assertEqual(jnlp["name"], "jnlp")
        env = {item["name"]: item["value"] for item in jnlp["env"]}
        self.assertTrue(env["PATH"].startswith("/fortifylab-tools/bin:"))
        for key in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO", "REQUESTS_CA_BUNDLE"):
            self.assertEqual(env[key], "/fortifylab-trust/ca-bundle.crt")
        self.assertEqual(env["FCLI_DATA_DIR"], "/fortifylab-trust/fcli-data")
        self.assertIn("trustStore=/fortifylab-trust/cacerts", env["JAVA_TOOL_OPTIONS"])
        volumes = {item["name"]: item for item in pod["volumes"]}
        self.assertEqual(volumes["fortifylab-ca"]["configMap"]["name"], "fortifylab-root-ca")
        self.assertEqual(volumes["fortifylab-tools"]["persistentVolumeClaim"]["claimName"], "jenkins-agent-tools")

    def test_fcli_version_defaults_to_the_lab_pin(self) -> None:
        text = render_values(FORTIFY_RECOMMENDED_FCLI_VERSION="7.7.7")
        self.assertIn('value: "7.7.7"', text)


@unittest.skipUnless(HAVE_CERT_TOOLS, "openssl, keytool, and envsubst are required")
class StartScriptTests(unittest.TestCase):
    """Run start.sh and destroy.sh against a fake `microk8s` that logs calls."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "repo"
        (self.home / "scripts").mkdir(parents=True)
        shutil.copytree(ROOT / "scripts/lib", self.home / "scripts/lib")
        shutil.copytree(APP, self.home / "apps/jenkins")
        self.certs = self.home / "certs"
        self.certs.mkdir()
        self.root_ca, _ = make_ca(self.certs, "rootCA")
        self.bin = Path(self._tmp.name) / "bin"
        self.bin.mkdir()
        self.log = Path(self._tmp.name) / "microk8s.log"
        fake = self.bin / "microk8s"
        fake.write_text(textwrap.dedent(f"""\
            #!/bin/bash
            printf '%s\\n' "$*" >>"{self.log}"
            case "$*" in
                *"get configmap coredns"*) printf '.:53 {{\\n    forward . /etc/resolv.conf\\n}}\\n' ;;
                *"--dry-run=client"*) printf 'kind: Generated\\n' ;;
                *"statefulset jenkins"*"metadata.generation"*) printf '%s' "${{FAKE_GENERATION:-2}}" ;;
                *"statefulset jenkins"*"observedGeneration"*) printf '%s' "${{FAKE_OBSERVED:-2}}" ;;
                *"statefulset jenkins"*"updateRevision"*) printf '%s' "${{FAKE_UPDATE_REV:-jenkins-new}}" ;;
                *"pod jenkins-0"*"controller-revision-hash"*) printf '%s' "${{FAKE_POD_REV:-jenkins-new}}" ;;
                *"pod jenkins-0"*"Ready"*) printf '%s' "${{FAKE_POD_READY:-True}}" ;;
            esac
            exit 0
        """), encoding="utf-8")
        fake.chmod(0o755)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_env(self, leaf_sans: str) -> None:
        leaf, _ = make_ca(self.certs, "tls", sans=leaf_sans)
        (self.home / ".env").write_text(textwrap.dedent(f"""\
            export DOMAIN=lab.example.test
            export NAMESPACE=fortify
            export DEFAULT_PASS=lab-secret-pass
            export ROOTCA_CERT={self.root_ca}
            export SERVER_CERT={leaf}
        """), encoding="utf-8")

    def run_script(self, name: str, **env: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        environment["FORTIFY_HOME_K8S"] = str(self.home)
        environment.pop("KUBECTL", None)
        environment.update(env)
        return subprocess.run(["bash", str(self.home / f"apps/jenkins/{name}")], check=False,
                              capture_output=True, text=True, env=environment)

    def calls(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_start_deploys_pinned_chart_with_lab_ca_and_admin_secret(self) -> None:
        self.write_env("DNS:lab.example.test,DNS:*.lab.example.test")
        result = self.run_script("start.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertIn(f"create configmap fortifylab-root-ca --from-file=rootCA.pem={self.root_ca}", calls)
        self.assertIn("create configmap jenkins-agent-init --from-file=agent-init.sh=", calls)
        self.assertIn("create secret generic jenkins-admin --from-literal=jenkins-admin-user=admin --from-literal=jenkins-admin-password=lab-secret-pass", calls)
        self.assertIn("helm repo add jenkins https://charts.jenkins.io --force-update", calls)
        self.assertRegex(calls, r"helm -n fortify upgrade -i jenkins jenkins/jenkins --version 5\.9\.64 -f \S+")
        self.assertIn("scale statefulset jenkins --replicas=1", calls)

    def test_start_replaces_a_stuck_pod_left_on_an_old_revision(self) -> None:
        # A crash-looping pod on the old spec blocks a StatefulSet rolling
        # update forever; start.sh must replace it so the fix can roll out.
        self.write_env("DNS:*.lab.example.test")
        result = self.run_script("start.sh", FAKE_POD_REV="jenkins-old", FAKE_POD_READY="False")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("delete pod jenkins-0 --wait=false", self.calls())
        self.assertIn("replacing it so the upgrade can roll out", result.stdout)

    def test_start_leaves_healthy_or_current_pods_alone(self) -> None:
        self.write_env("DNS:*.lab.example.test")
        cases = (
            {"FAKE_POD_REV": "jenkins-old", "FAKE_POD_READY": "True"},   # normal rolling update
            {"FAKE_POD_REV": "jenkins-new", "FAKE_POD_READY": "False"},  # new pod still starting
        )
        for env in cases:
            with self.subTest(**env):
                self.log.unlink(missing_ok=True)
                result = self.run_script("start.sh", **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("delete pod jenkins-0", self.calls())

    def test_start_refuses_a_certificate_that_does_not_cover_jenkins(self) -> None:
        self.write_env("DNS:ssc.lab.example.test,DNS:sast.lab.example.test")
        result = self.run_script("start.sh")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not cover jenkins.lab.example.test", result.stderr)
        self.assertNotIn("helm", self.calls())

    def test_start_rejects_unknown_fcli_mode(self) -> None:
        self.write_env("DNS:*.lab.example.test")
        result = self.run_script("start.sh", FORTIFY_JENKINS_FCLI_INSTALL="sometimes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FORTIFY_JENKINS_FCLI_INSTALL must be auto or manual", result.stderr)

    def test_destroy_keeps_data_unless_confirmed(self) -> None:
        self.write_env("DNS:*.lab.example.test")
        kept = self.run_script("destroy.sh")
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertIn("Kept Jenkins data volumes", kept.stdout)
        self.assertNotIn("delete -f -", self.calls())
        deleted = self.run_script("destroy.sh", JENKINS_DESTROY_DATA="1")
        self.assertEqual(deleted.returncode, 0, deleted.stderr)
        self.assertIn("delete -f - --ignore-not-found", self.calls())


class WizardWiringTests(unittest.TestCase):
    def run_wizard(self, body: str, user_input: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", 'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; title() { :; }; sleep() { :; }; press_any() { :; }; ' + body,
             "jenkins-wizard-test", str(WIZARD)],
            cwd=ROOT, input=user_input, check=False, capture_output=True, text=True,
        )

    def test_lab_hostnames_include_jenkins(self) -> None:
        result = self.run_wizard("DOMAIN=lab.example.test; fortify_lab_hostnames")
        self.assertIn("jenkins.lab.example.test", result.stdout.split())

    def test_main_and_more_menus_offer_integrations(self) -> None:
        menu = (ROOT / "scripts/wizard/menu.sh").read_text(encoding="utf-8")
        self.assertIn("i. Integrations (Jenkins CI)", menu)
        self.assertIn("[Ii]) integrations_menu", menu)
        self.assertIn("22)  integrations_menu", menu)

    def test_integrations_menu_dispatches_jenkins_actions(self) -> None:
        result = self.run_wizard(
            "jenkins_integration_status() { echo STATUS; }; "
            "run_app_scripts() { echo \"RUN $1 data=${JENKINS_DESTROY_DATA:-unset}\"; }; "
            "jenkins_integration_start() { echo START; }; "
            "integrations_menu",
            user_input="1\n1\n2\n3\ny\nn\nr\nr\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("START", result.stdout)
        self.assertIn("RUN apps/jenkins/stop.sh", result.stdout)
        self.assertIn("RUN apps/jenkins/destroy.sh data=0", result.stdout)

    def test_jenkins_is_not_part_of_the_lab_lifecycle(self) -> None:
        registry = (ROOT / "scripts/wizard/app-registry.sh").read_text(encoding="utf-8")
        guided = (ROOT / "scripts/wizard/guided.sh").read_text(encoding="utf-8")
        self.assertNotIn("jenkins", registry.lower())
        self.assertNotIn("jenkins", guided.lower())

    def test_access_help_never_prints_the_password(self) -> None:
        result = self.run_wizard("DEFAULT_PASS=super-secret-value; JENKINS_ADMIN_PASSWORD=other-secret; jenkins_integration_access_help")
        self.assertIn("pipeline {", result.stdout)
        self.assertNotIn("super-secret-value", result.stdout)
        self.assertNotIn("other-secret", result.stdout)


if __name__ == "__main__":
    unittest.main()
