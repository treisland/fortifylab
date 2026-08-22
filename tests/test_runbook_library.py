"""Contracts for the Solutions Engineer Runbook Library."""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.wizard_source import read_wizard_source


ROOT = Path(__file__).resolve().parents[1]
WIZARD = read_wizard_source(ROOT)


class RunbookLibraryTests(unittest.TestCase):
    def run_wizard_functions(
        self, body: str, *, runbook_root: Path | None = None, user_input: str = ""
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["HOME"] = str(Path(directory) / "home")
            environment["XDG_STATE_HOME"] = str(Path(directory) / "state")
            environment["FORTIFY_WIZARD_LOG_FILE"] = str(Path(directory) / "wizard.log")
            command = 'export WIZARD_NOMAIN=1 NO_COLOR=1; source "$1"; '
            if runbook_root is not None:
                command += 'RUNBOOK_ROOT_DIR="$2"; shift; '
            command += "title() { :; }; press_any() { :; }; sleep() { :; }; " + body
            args = ["bash", "-c", command, "runbook-test", str(ROOT / "start_wizard.sh")]
            if runbook_root is not None:
                args.append(str(runbook_root))
            return subprocess.run(
                args,
                cwd=ROOT,
                input=user_input,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )

    def make_runbook(self, root: Path, relative: str, body: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_menu_and_loader_include_runbook_library(self) -> None:
        self.assertIn("source_wizard_module runbooks.sh", (ROOT / "start_wizard.sh").read_text(encoding="utf-8"))
        self.assertIn("runbooks_menu()", WIZARD)
        self.assertIn("Runbook Library", WIZARD)
        self.assertIn("16)  runbooks_menu ;;", WIZARD)

    def test_template_and_local_folder_contract_are_documented(self) -> None:
        template = (ROOT / "runbooks/templates/shell-runbook.sh").read_text(encoding="utf-8")
        docs = (ROOT / "docs/operations/runbooks.md").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("fortifylab-runbook: true", template)
        self.assertIn("params:", template)
        self.assertIn("defaultFromEnv", template)
        self.assertIn("runbooks/local/*", gitignore)
        self.assertIn("local-first", docs)
        self.assertIn("Parameter names become uppercase environment variables", docs)

    def test_discovery_lists_only_opted_in_runbooks_sorted_by_source_category_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runbook_root = Path(directory)
            self.make_runbook(
                runbook_root,
                "training/z-last.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Training Later
                # description: Later training runbook.
                # category: FCLI
                # risk: low
                # order: 30
                echo training
                """,
            )
            self.make_runbook(
                runbook_root,
                "official/a-first.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Official First
                # description: Official runbook.
                # category: Diagnostics
                # risk: low
                # order: 10
                echo official
                """,
            )
            self.make_runbook(runbook_root, "local/not-listed.sh", "#!/usr/bin/env bash\necho nope\n")
            result = self.run_wizard_functions("runbook_discover_records", runbook_root=runbook_root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Official First", result.stdout)
            self.assertIn("Training Later", result.stdout)
            self.assertNotIn("not-listed", result.stdout)
            self.assertLess(result.stdout.index("Official First"), result.stdout.index("Training Later"))


    def test_runbook_domains_are_first_level_menu_groups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runbook_root = Path(directory)
            self.make_runbook(
                runbook_root,
                "official/ssc-login.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: SSC Login
                # description: Local SSC login runbook.
                # domain: Local lab: SSC
                # category: Sessions
                # risk: low
                # order: 10
                echo ssc
                """,
            )
            self.make_runbook(
                runbook_root,
                "training/fod-login.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: FoD Login
                # description: FoD SaaS login runbook.
                # domain: Fortify on Demand
                # category: Sessions
                # risk: low
                # order: 20
                echo fod
                """,
            )
            result = self.run_wizard_functions("runbooks_menu", runbook_root=runbook_root, user_input="b\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Local lab: SSC", result.stdout)
            self.assertIn("Fortify on Demand", result.stdout)


    def test_fcli_operator_runbooks_are_documented_and_separated(self) -> None:
        official = ROOT / "runbooks" / "official" / "fcli"
        fod = ROOT / "runbooks" / "training" / "fcli-fod"
        docs = (ROOT / "docs" / "runbooks" / "fcli.md").read_text(encoding="utf-8")
        expected_files = (
            official / "inspect-fcli-foundation.sh",
            official / "configure-lab-trust.sh",
            official / "ssc-token-guidance.sh",
            official / "local-ssc-login-discovery.sh",
            official / "local-ssc-create-appversion.sh",
            official / "local-ssc-upload-fpr.sh",
            official / "local-ssc-policy-check.sh",
            official / "local-ssc-appversion-summary.sh",
            official / "local-ssc-session-doctor.sh",
            official / "local-ssc-inventory.sh",
            official / "local-ssc-logout-cleanup.sh",
            fod / "00-fod-env-session-check.sh",
            fod / "20-package-and-upload.sh",
            fod / "50-release-summary.sh",
        )
        for path in expected_files:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("fortifylab-runbook: true", text)
                self.assertIn("# domain:", text)
        self.assertIn("official [fcli v3 documentation]", docs.lower())
        self.assertIn("Local SSC", docs)
        self.assertIn("configure-lab-trust.sh", docs)
        self.assertIn("ssc-token-guidance.sh", docs)
        self.assertIn("trust -> token guidance -> login", docs)
        self.assertIn("FoD", docs)
        self.assertIn("external SaaS", (fod / "README.md").read_text(encoding="utf-8"))

    def test_local_ssc_fcli_runbooks_have_bounded_mutation_contracts(self) -> None:
        official = ROOT / "runbooks" / "official" / "fcli"
        create = (official / "local-ssc-create-appversion.sh").read_text(encoding="utf-8")
        upload = (official / "local-ssc-upload-fpr.sh").read_text(encoding="utf-8")
        policy = (official / "local-ssc-policy-check.sh").read_text(encoding="utf-8")
        summary = (official / "local-ssc-appversion-summary.sh").read_text(encoding="utf-8")
        common = (official / "ssc-common.bash").read_text(encoding="utf-8")

        for text in (create, upload, policy, summary):
            with self.subTest(runbook=text.splitlines()[2]):
                self.assertIn("# domain: Local lab: SSC", text)
                self.assertIn("default: fortifylab", text)
                self.assertIn("ssc_require_fcli", text)
                self.assertIn("ssc_require_command_help", text)
                self.assertIn("--ssc-session", text)
                self.assertNotIn("TOKEN", text)
                self.assertNotIn("SECRET", text)

        self.assertIn("CONFIRM_LOCAL_SSC_CREATE", create)
        self.assertIn("Creation skipped", create)
        self.assertIn("--skip-if-exists", create)
        self.assertIn("--auto-required-attrs", create)
        self.assertIn("CONFIRM_LOCAL_SSC_UPLOAD", upload)
        self.assertIn("Upload skipped", upload)
        self.assertIn('[[ ! -f "$FPR_FILE" ]]', upload)
        self.assertIn('[[ ! -r "$FPR_FILE" ]]', upload)
        self.assertIn("*.fpr|*.FPR", upload)
        self.assertIn("check-policy", policy)
        self.assertIn("appversion-summary", summary)
        self.assertIn("${SESSION_NAME:-fortifylab}", common)

    def test_local_ssc_trust_and_token_guidance_are_secret_safe(self) -> None:
        official = ROOT / "runbooks" / "official" / "fcli"
        trust = (official / "configure-lab-trust.sh").read_text(encoding="utf-8")
        token = (official / "ssc-token-guidance.sh").read_text(encoding="utf-8")
        login = (official / "local-ssc-login-discovery.sh").read_text(encoding="utf-8")

        self.assertIn("# domain: Local lab: SSC", trust)
        self.assertIn("# category: FCLI trust", trust)
        self.assertIn("FCLI_TRUSTSTORE", trust)
        self.assertIn("FCLI_TRUSTSTORE_TYPE", trust)
        self.assertIn("<DEFAULT_PASS from your private .env>", trust)
        self.assertNotIn('export FCLI_TRUSTSTORE_PWD="$DEFAULT_PASS"', trust)
        self.assertIn("# category: FCLI authentication", token)
        self.assertIn("unset $TOKEN_ENV_VAR", token)
        self.assertIn("Never store SSC token values", token)
        self.assertIn("PKIX", login)
        self.assertIn("Configure fcli trust for lab TLS", login)

    def test_official_fcli_runbooks_are_shell_syntax_valid(self) -> None:
        scripts = sorted((ROOT / "runbooks" / "official" / "fcli").glob("*.sh"))
        scripts.append(ROOT / "runbooks" / "official" / "fcli" / "ssc-common.bash")
        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    ["bash", "-n", str(script)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_local_ssc_fcli_runbooks_are_bounded_and_runtime_checked(self) -> None:
        official = ROOT / "runbooks" / "official" / "fcli"
        expected = {
            "local-ssc-session-doctor.sh",
            "local-ssc-inventory.sh",
            "local-ssc-logout-cleanup.sh",
        }
        for filename in expected:
            with self.subTest(filename=filename):
                text = (official / filename).read_text(encoding="utf-8")
                self.assertIn("# domain: Local lab: SSC", text)
                self.assertIn("# requires: bash", text)
                self.assertNotIn("# requires: fcli", text)
                self.assertIn("default: fortifylab", text)
                self.assertIn("resolve_fcli_bin", text)
                self.assertIn("--help", text)
                self.assertIn("No token values", text)

    def test_validation_reports_missing_metadata_and_required_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runbook_root = Path(directory)
            bad = self.make_runbook(
                runbook_root,
                "official/bad.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Broken
                # risk: weird
                # requires: definitely_missing_tool_for_fortifylab_tests
                echo broken
                """,
            )
            result = self.run_wizard_functions(
                f'runbook_parse_file {bad}; runbook_validate_current_metadata {bad} || printf "%s\\n" "${{RUNBOOK_PARSE_ERRORS[@]}}"',
                runbook_root=runbook_root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("missing required metadata: description", result.stdout)
            self.assertIn("invalid risk", result.stdout)
            self.assertIn("missing required tools", result.stdout)

    def test_parameters_are_passed_as_environment_variables_and_output_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runbook_root = Path(directory) / "runbooks"
            script = self.make_runbook(
                runbook_root,
                "training/submit-sast.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Submit SAST demo
                # description: Exercises parameter passing for an FCLI-style scan runbook.
                # category: FCLI Training
                # risk: low
                # order: 20
                # requires: bash
                # params:
                #   - name: app_name
                #     description: SSC application name.
                #     default: JuiceShop
                #   - name: version_name
                #     description: SSC version name.
                #     default: training
                set -euo pipefail
                echo "app=${APP_NAME} version=${VERSION_NAME}"
                echo "token=super-secret-value"
                """,
            )
            result = self.run_wizard_functions(
                f'runbook_parse_file {script}; runbook_init_param_values; '
                'RUNBOOK_SELECTED_PARAM_VALUES[0]=CustomerPortal; '
                f'runbook_run {script}',
                runbook_root=runbook_root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("app=CustomerPortal version=training", result.stdout)
            self.assertIn("token=<redacted>", result.stdout)
            self.assertNotIn("super-secret-value", result.stdout)

    def test_parameter_forms_and_previews_redact_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runbook_root = Path(directory) / "runbooks"
            script = self.make_runbook(
                runbook_root,
                "ssc/login.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: SSC login
                # description: Login example.
                # category: SSC
                # risk: medium
                # params:
                #   - name: ssc_token
                #     description: SSC token.
                #     default: secret-token-value
                #   - name: app_name
                #     description: Application name.
                #     default: Demo
                echo ok
                """,
            )
            result = self.run_wizard_functions(
                f'runbook_parse_file {script}; runbook_init_param_values; '
                f'runbook_print_params; runbook_show_resolved_command {script}',
                runbook_root=runbook_root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ssc_token", result.stdout)
            self.assertIn("<redacted>", result.stdout)
            self.assertIn("APP_NAME=Demo", result.stdout)
            self.assertNotIn("secret-token-value", result.stdout)

    def test_resolved_command_preview_shows_parameter_exports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runbook_root = Path(directory) / "runbooks"
            script = self.make_runbook(
                runbook_root,
                "training/generate-gha.sh",
                """
                #!/usr/bin/env bash
                # fortifylab-runbook: true
                # name: Generate GHA
                # description: Example generator.
                # category: CI/CD Examples
                # risk: low
                # params:
                #   - name: target_repo
                #     description: Target repository path.
                #     required: true
                #   - name: app_version
                #     description: App version.
                #     default: JuiceShop:training
                echo ok
                """,
            )
            result = self.run_wizard_functions(
                f'runbook_parse_file {script}; runbook_init_param_values; '
                'RUNBOOK_SELECTED_PARAM_VALUES[0]=/tmp/demo; '
                f'runbook_show_resolved_command {script}',
                runbook_root=runbook_root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TARGET_REPO=/tmp/demo", result.stdout)
            self.assertIn("APP_VERSION=JuiceShop:training", result.stdout)
            self.assertIn("bash", result.stdout)
