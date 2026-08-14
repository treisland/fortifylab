"""Static safety contracts for the wizard-only deployment repository."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WizardContractTests(unittest.TestCase):
    def test_fresh_install_versions_match_current_chart_contracts(self) -> None:
        environment = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn('FORTIFY_SSC_CHART_VERSION="26.2.0-1"', environment)
        self.assertIn('FORTIFY_SCSAST_CHART_VERSION="26.2.0-1"', environment)

    def test_dependency_waits_abort_the_deployment(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        for gate in ("mysql", "postgresql", "ssc", "lim"):
            self.assertIn(f"{gate}_ready()", wizard)
        for probe in (
            "health_mysql_statefulset_probe && health_mysql_query",
            "health_postgresql_statefulset_probe && health_postgresql_query",
            "health_ssc_statefulset_probe && health_ssc_service_probe",
            "health_ssc_ingress_probe && health_ssc_http_probe",
            "health_lim_statefulset_probe && health_lim_service_probe",
            "health_lim_ingress_probe && health_lim_http_probe",
        ):
            self.assertIn(probe, wizard)
        self.assertIn("guided_run_and_verify mysql", wizard)
        self.assertIn("guided_run_and_verify ssc", wizard)
        self.assertNotIn('"pod/$pod" || true', wizard)

    def test_fresh_install_refuses_existing_managed_releases(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        self.assertIn("fresh_deployment_guard()", wizard)
        self.assertIn("Managed releases already exist", wizard)
        self.assertIn("Resume or repair deployment", wizard)
        self.assertIn("Manage individual components -> Start / Upgrade", wizard)
        self.assertIn("fresh_deployment_guard ||", wizard)
        preflight = wizard.split("preflight_check()", 1)[1].split("deploy_step()", 1)[0]
        self.assertNotIn("Managed releases already exist", preflight)

    def test_removed_products_do_not_return(self) -> None:
        self.assertFalse((ROOT / "manager").exists())
        self.assertFalse((ROOT / "supervisor").exists())
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True
        ).splitlines()
        self.assertFalse(any(path.startswith("apps/jenkins/") for path in tracked))
        self.assertFalse(any(path.startswith("apps/sonatype/") for path in tracked))

    def test_credentials_are_not_printed_or_passed_to_helm(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        sast = (ROOT / "apps/scsast/start.sh").read_text(encoding="utf-8")
        app_credentials = wizard.split("show_app_creds()", 1)[1].split(
            "# License menu", 1
        )[0]
        url_credentials = wizard.split("credential_retrieval_commands()", 1)[1].split(
            "versions_menu()", 1
        )[0]
        self.assertNotIn("base64 -d", app_credentials)
        self.assertIn("Show retrieval commands", url_credentials)
        self.assertIn("base64 -d", url_credentials)
        self.assertIn("Type REVEAL to display this value once", wizard)
        self.assertNotIn('controller.sscScanCentralCtrlToken="$token"', wizard)
        self.assertIn("--set-string controller.sscScanCentralCtrlToken=", wizard)
        for legacy_value in (
            "secrets.fortifyLicense=",
            "secrets.workerAuthToken=",
            "secrets.clientAuthToken=",
            "secrets.sscScanCentralCtrlSecret=",
        ):
            self.assertIn(legacy_value, wizard)
        self.assertNotIn("controller.sscScanCentralCtrlToken", sast)
        self.assertIn('read -rsp "Paste ControllerToken', wizard)
        self.assertIn("--patch-file /dev/stdin", wizard)
        self.assertIn("stored in Kubernetes Secret lim-admin-credentials", wizard)
        self.assertIn("refer to the SSC documentation for the default password", wizard)

    def test_controller_token_update_keeps_value_out_of_output_and_arguments(self) -> None:
        token = "synthetic-controller-secret"
        command = r'''
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            NAMESPACE=fortify
            HELM=fake_helm
            KUBECTL=fake_kubectl
            fake_helm() { return 0; }
            fake_kubectl() {
                if [[ "$*" == *" patch secret "* ]]; then cat >/dev/null; fi
                return 0
            }
            export -f fake_helm fake_kubectl
            configure_ssc_token
        '''
        with subprocess.Popen(
            ["bash", "-c", command, "token-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            stdout, stderr = process.communicate(token + "\n", timeout=10)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertNotIn(token, stdout + stderr)

    def test_ssc_and_lim_ingress_hosts_are_rendered_from_env(self) -> None:
        ssc_ingress = (ROOT / "apps" / "ssc" / "ingress.yaml").read_text(encoding="utf-8")
        lim_ingress = (ROOT / "apps" / "lim" / "ingress.yaml").read_text(encoding="utf-8")
        ssc_start = (ROOT / "apps" / "ssc" / "start.sh").read_text(encoding="utf-8")
        lim_start = (ROOT / "apps" / "lim" / "start.sh").read_text(encoding="utf-8")
        ssc_destroy = (ROOT / "apps" / "ssc" / "destroy.sh").read_text(encoding="utf-8")
        lim_destroy = (ROOT / "apps" / "lim" / "destroy.sh").read_text(encoding="utf-8")
        self.assertIn("${SSC}", ssc_ingress)
        self.assertIn("${LIM}", lim_ingress)
        self.assertIn("namespace: ${NAMESPACE}", ssc_ingress)
        self.assertIn("namespace: ${NAMESPACE}", lim_ingress)
        self.assertNotIn("ssc.fortifydemo.com", ssc_ingress)
        self.assertNotIn("lim.fortifydemo.com", lim_ingress)
        self.assertIn("envsubst '${SSC} ${NAMESPACE} ${TRAEFIK_SSC_UPLOAD_MIDDLEWARE}'", ssc_start)
        self.assertIn("envsubst '${LIM} ${NAMESPACE}'", lim_start)
        self.assertIn("delete ingress ssc-ingress", ssc_destroy)
        self.assertIn("delete ingress lim-ingress", lim_destroy)

    def test_lab_ingresses_support_traefik_backed_microk8s(self) -> None:
        ssc_ingress = (ROOT / "apps" / "ssc" / "ingress.yaml").read_text(encoding="utf-8")
        lim_ingress = (ROOT / "apps" / "lim" / "ingress.yaml").read_text(encoding="utf-8")
        dashboard = (ROOT / "apps" / "kubernetes-dashboard" / "dashboard.yaml").read_text(encoding="utf-8")
        ssc_start = (ROOT / "apps" / "ssc" / "start.sh").read_text(encoding="utf-8")
        ssc_destroy = (ROOT / "apps" / "ssc" / "destroy.sh").read_text(encoding="utf-8")
        lim_start = (ROOT / "apps" / "lim" / "start.sh").read_text(encoding="utf-8")
        dashboard_deploy = (ROOT / "apps" / "kubernetes-dashboard" / "deploy.sh").read_text(encoding="utf-8")
        middleware = (ROOT / "apps" / "ssc" / "traefik-upload-middleware.yaml").read_text(encoding="utf-8")
        traefik_backend = (ROOT / "scripts" / "lib" / "traefik-backend.sh").read_text(encoding="utf-8")
        scsast = (ROOT / "apps" / "scsast" / "start.sh").read_text(encoding="utf-8")
        scdast = (ROOT / "apps" / "scdast" / "core" / "start.sh").read_text(encoding="utf-8")

        for manifest in (ssc_ingress, lim_ingress, dashboard):
            self.assertIn("nginx.ingress.kubernetes.io/backend-protocol", manifest)
            self.assertIn("traefik.ingress.kubernetes.io/router.tls", manifest)
            self.assertIn("traefik.ingress.kubernetes.io/service.serversscheme", manifest)

        self.assertIn("nginx.ingress.kubernetes.io/proxy-body-size", ssc_ingress)
        self.assertIn("traefik.ingress.kubernetes.io/router.middlewares", ssc_ingress)
        self.assertIn("${TRAEFIK_SSC_UPLOAD_MIDDLEWARE}", ssc_ingress)
        self.assertIn("middlewares.traefik.io", ssc_start)
        self.assertIn("traefik-upload-middleware.yaml", ssc_start)
        self.assertIn("delete middleware.traefik.io fortify-upload-buffer", ssc_destroy)
        self.assertIn("maxRequestBodyBytes: 1073741824", middleware)
        self.assertIn("namespace: ${NAMESPACE}", middleware)

        for script in (ssc_start, lim_start, dashboard_deploy, scsast):
            self.assertIn("scripts/lib/traefik-backend.sh", script)
            self.assertIn("fortify_annotate_traefik_https_service", script)
        self.assertIn('fortify_annotate_traefik_https_service "$NAMESPACE" ssc-service', ssc_start)
        self.assertIn('fortify_annotate_traefik_https_service "$NAMESPACE" lim', lim_start)
        self.assertIn('fortify_annotate_traefik_https_service "$DASHBOARD_NAMESPACE" "$DASHBOARD_SERVICE"', dashboard_deploy)
        self.assertIn('fortify_annotate_traefik_https_service "$NAMESPACE" scancentral-sast-controller', scsast)
        self.assertIn("kind: ServersTransport", traefik_backend)
        self.assertIn("insecureSkipVerify: true", traefik_backend)
        self.assertIn("traefik.ingress.kubernetes.io/service.serverstransport", traefik_backend)
        self.assertIn("traefik.ingress.kubernetes.io/service.serversscheme=https", traefik_backend)

        self.assertIn("--set-string controller.ingress.annotations", scsast)
        self.assertIn("traefik\\.ingress\\.kubernetes\\.io/router\\.tls", scsast)
        self.assertIn("traefik\\.ingress\\.kubernetes\\.io/service\\.serversscheme", scsast)
        self.assertIn("--set-string api.ingress.annotations", scdast)
        self.assertIn("traefik\\.ingress\\.kubernetes\\.io/router\\.tls", scdast)
        self.assertIn("api.ingress.className=public", scdast)
        self.assertNotIn("api.ingress.annotations.\"nginx\\\\.ingress", scdast)
        self.assertNotIn("api.ingress.annotations.\"traefik\\\\.ingress\\\\.kubernetes\\\\.io/service", scdast)


    def test_app_starts_refresh_coredns_before_hostname_based_workloads(self) -> None:
        for relative in (
            "apps/ssc/start.sh",
            "apps/lim/start.sh",
            "apps/scsast/start.sh",
            "apps/scdast/core/start.sh",
            "apps/scdast/scanner/start.sh",
        ):
            script = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("coredns-lab-hosts.sh", script, relative)
            self.assertIn("fortify_ensure_coredns_lab_hosts", script, relative)

    def test_wizard_dns_uses_shared_coredns_helper(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        helper = (ROOT / "scripts/lib/coredns-lab-hosts.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/lib/coredns-lab-hosts.sh", wizard)
        self.assertIn("fortify_ensure_coredns_lab_hosts || return 1", wizard)
        self.assertIn("# fortifylab hosts begin", helper)
        self.assertIn("ScanCentral SAST workers call", wizard)

    def test_guided_status_surfaces_endpoint_and_hostname_detail(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        self.assertIn("guided_component_endpoint_detail", wizard)
        self.assertIn("health_http_detail", wizard)
        self.assertIn("FORTIFY_HEALTH_HTTP_MAX_TIME=3", wizard)
        self.assertIn("Service %s has no ready endpoints yet.", wizard)
        self.assertIn("Ingress %s does not contain host %s yet.", wizard)
        self.assertIn("lab_hosts_resolution_detail", wizard)
        self.assertIn("Lab hostnames resolve to loopback", wizard)
        self.assertIn("ip=$(lab_node_ip)", wizard)

    def test_create_secrets_configures_microk8s_ingress_default_tls(self) -> None:
        create_secrets = (ROOT / "scripts" / "create-secrets.sh").read_text(encoding="utf-8")
        self.assertIn("configure_microk8s_ingress_default_tls()", create_secrets)
        self.assertIn("--default-ssl-certificate", create_secrets)
        self.assertIn('cert_ref="$NAMESPACE/tls"', create_secrets)
        tls_create = create_secrets.index('create secret tls tls')
        tls_hook = create_secrets.index('configure_microk8s_ingress_default_tls', tls_create)
        self.assertLess(tls_create, tls_hook)
        self.assertIn("TRAEFIK DEFAULT CERT", create_secrets)

    def test_registry_credentials_refresh_before_image_pull_steps(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        create_secrets = (ROOT / "scripts" / "create-secrets.sh").read_text(encoding="utf-8")
        helper = (ROOT / "scripts" / "lib" / "registry-credentials.sh").read_text(encoding="utf-8")
        self.assertIn('source "$FORTIFY_HOME_K8S/scripts/lib/registry-credentials.sh"', wizard)
        self.assertIn('source "$FORTIFY_HOME_K8S/scripts/lib/registry-credentials.sh"', create_secrets)
        self.assertIn("materialize_registry_auth_config()", helper)
        self.assertIn("docker-credential-{helper}", helper)
        self.assertIn("credsStore", helper)
        self.assertIn("registry-1.docker.io", helper)
        self.assertIn("https://index.docker.io/v1/", helper)
        self.assertIn('ensure_registry_credentials "$operation"', wizard)
        self.assertIn('action=operation_start step=$operation', wizard)
        self.assertIn("mysql|postgresql|ssc|lim|sast|dast)", wizard)
        self.assertNotIn("mysql|postgresql|ssc|lim|sast|dast|secrets)", wizard)
        self.assertIn('--dry-run=client -o yaml | $KUBECTL -n "$NAMESPACE" apply -f -', helper)
        self.assertIn("create secret generic regcred", helper)
        self.assertIn("--type=kubernetes.io/dockerconfigjson", helper)
        self.assertIn("refresh_registry_credentials", create_secrets)
        dispatcher = wizard.split('run_deployment_operation() {', 1)[1].split('guided_run_and_verify()', 1)[0]
        self.assertLess(dispatcher.index('ensure_registry_credentials "$operation"'), dispatcher.index('case "$operation" in'))

    def test_registry_materializer_writes_dockerhub_aliases(self) -> None:
        helper = ROOT / "scripts" / "lib" / "registry-credentials.sh"
        auth = base64.b64encode(b"fortify-user:fortify-token").decode("ascii")
        with tempfile.TemporaryDirectory() as temp_dir:
            docker_config = Path(temp_dir) / "config.json"
            docker_config.write_text(
                json.dumps({"auths": {"https://index.docker.io/v1/": {"auth": auth}}}),
                encoding="utf-8",
            )
            command = """
                source "$1"
                DOCKER_CONFIG_PATH="$2"
                materialized="$(materialize_registry_auth_config)"
                cat "$materialized"
                rm -f "$materialized"
            """
            output = subprocess.check_output(
                ["bash", "-c", command, "registry-test", str(helper), str(docker_config)],
                cwd=ROOT,
                text=True,
            )
        materialized = json.loads(output)
        auths = materialized["auths"]
        for server in (
            "https://index.docker.io/v1/",
            "registry-1.docker.io",
            "https://registry-1.docker.io",
            "index.docker.io",
            "docker.io",
        ):
            self.assertEqual(auths[server]["auth"], auth)

    def test_registry_materializer_resolves_docker_credential_helper(self) -> None:
        helper = ROOT / "scripts" / "lib" / "registry-credentials.sh"
        expected_auth = base64.b64encode(b"helper-user:helper-token").decode("ascii")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            docker_config = temp_path / "config.json"
            docker_config.write_text(
                json.dumps({"auths": {"https://index.docker.io/v1/": {}}, "credsStore": "fortifytest"}),
                encoding="utf-8",
            )
            fake_helper = temp_path / "docker-credential-fortifytest"
            fake_helper.write_text(
                """#!/bin/sh
if [ "$1" = get ]; then
  cat >/dev/null
  printf %s '{"Username":"helper-user","Secret":"helper-token"}'
  exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            fake_helper.chmod(0o755)
            command = """
                source "$1"
                PATH="$2:$PATH"
                DOCKER_CONFIG_PATH="$3"
                materialized="$(materialize_registry_auth_config)"
                cat "$materialized"
                rm -f "$materialized"
            """
            output = subprocess.check_output(
                ["bash", "-c", command, "registry-test", str(helper), str(temp_path), str(docker_config)],
                cwd=ROOT,
                text=True,
            )
        materialized = json.loads(output)
        self.assertEqual(materialized["auths"]["registry-1.docker.io"]["auth"], expected_auth)

    def test_microk8s_installer_adds_group_and_guides_shell_refresh(self) -> None:
        installer = (ROOT / "scripts" / "install_microk8s.sh").read_text(encoding="utf-8")
        self.assertIn('sudo usermod -aG microk8s "$target_user"', installer)
        self.assertIn('sudo chown -R "$target_user:$target_user" "$target_home/.kube"', installer)
        self.assertIn("newgrp microk8s", installer)
        self.assertIn("sudo microk8s status --wait-ready", installer)

    def test_app_start_scripts_validate_ingress_hosts_before_deploying(self) -> None:
        helper = ROOT / "scripts" / "lib" / "k8s-hostnames.sh"
        helper_text = helper.read_text(encoding="utf-8")
        self.assertIn("fortify_require_k8s_hostname", helper_text)
        self.assertIn("lowercase DNS name", helper_text)

        command = "source \"$1\"; fortify_require_k8s_hostname SSC LIM"
        result = subprocess.run(
            ["bash", "-c", command, "hostname-test", str(helper)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid SSC for Kubernetes ingress: LIM", result.stderr)

        valid = subprocess.run(
            ["bash", "-c", "source \"$1\"; fortify_require_k8s_hostname SSC ssc.fortifydemo.com", "hostname-test", str(helper)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)

        for script in (
            ROOT / "apps" / "ssc" / "start.sh",
            ROOT / "apps" / "lim" / "start.sh",
            ROOT / "apps" / "scsast" / "start.sh",
            ROOT / "apps" / "scdast" / "core" / "start.sh",
        ):
            text = script.read_text(encoding="utf-8")
            self.assertIn("scripts/lib/k8s-hostnames.sh", text)
            self.assertLess(text.index("fortify_require_k8s_hostname"), text.index("microk8s helm"))



    def test_fcli_tools_menu_is_warning_only_and_version_pinned(self) -> None:
        wizard = (ROOT / "start_wizard.sh").read_text(encoding="utf-8")
        environment = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn('FORTIFY_RECOMMENDED_FCLI_VERSION="3.23.3"', environment)
        self.assertIn('FORTIFY_FCLI_INSTALL_DIR="$HOME/fortify/tools/bin"', environment)
        self.assertIn("Tools and FCLI readiness", wizard)
        self.assertIn("fcli_tools_menu()", wizard)
        self.assertIn("fcli_install_or_update()", wizard)
        self.assertIn("FCLI missing; recommended", wizard)
        self.assertIn("does not block infrastructure deployment", wizard)
        preflight = wizard.split("preflight_check()", 1)[1].split("deploy_step()", 1)[0]
        self.assertNotIn("fcli", preflight.lower())

    def test_fcli_command_templates_are_secret_safe(self) -> None:
        command = """
            export WIZARD_NOMAIN=1 NO_COLOR=1
            source "$1"
            DOMAIN=fortifydemo.test
            SSC_URL=https://ssc.fortifydemo.test
            SCSAST_CTRL_URL=https://sast.fortifydemo.test/scancentral-ctrl/
            FORTIFY_SECRET_TOKEN=super-secret-token
            SCANCENTRAL_CLIENT_AUTH_TOKEN=actual-client-token
            FOD_CLIENT_SECRET=actual-fod-secret
            fcli_print_command_templates
        """
        output = subprocess.check_output(
            ["bash", "-c", command, "fcli-template-test", str(ROOT / "start_wizard.sh")],
            cwd=ROOT,
            text=True,
        )
        self.assertIn("fcli ssc session login", output)
        self.assertIn("https://ssc.fortifydemo.test", output)
        self.assertIn("<SSC_TOKEN_OR_PROMPT>", output)
        self.assertIn("<SCANCENTRAL_CLIENT_AUTH_TOKEN>", output)
        self.assertIn("FoD optional templates", output)
        self.assertNotIn("super-secret-token", output)
        self.assertNotIn("actual-client-token", output)
        self.assertNotIn("actual-fod-secret", output)

if __name__ == "__main__":
    unittest.main()
