"""Unit tests for fortifylab.services.urls_credentials_service (#446 slice 4)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fortifylab.core.command import CommandResult  # noqa: E402
from fortifylab.services.urls_credentials_service import CREDENTIAL_CHECKS, UrlsCredentialsService  # noqa: E402


class SecretKeyExistsTests(unittest.TestCase):
    def test_present_when_command_succeeds_with_nonempty_output(self) -> None:
        service = UrlsCredentialsService(runner=lambda args: CommandResult(args, 0, "c29tZS12YWx1ZQ==", "", 0.0))
        self.assertTrue(service.secret_key_exists("lim-admin-credentials", "password"))

    def test_absent_when_command_fails(self) -> None:
        service = UrlsCredentialsService(runner=lambda args: CommandResult(args, 1, "", "not found", 0.0))
        self.assertFalse(service.secret_key_exists("lim-admin-credentials", "password"))

    def test_absent_when_key_exists_but_is_empty(self) -> None:
        # jsonpath on a missing *key* (vs missing secret) can still exit 0
        # with empty output -- must not count as "present".
        service = UrlsCredentialsService(runner=lambda args: CommandResult(args, 0, "", "", 0.0))
        self.assertFalse(service.secret_key_exists("fortify-secrets", "some-other-key"))

    def test_return_value_is_strictly_boolean(self) -> None:
        # Guards the "safe boolean" boundary flagged in security review: a
        # future refactor that returns the CommandResult (or its stdout)
        # instead of a bool would silently start leaking secret material
        # through this function's return value.
        present = UrlsCredentialsService(runner=lambda args: CommandResult(args, 0, "c29tZS12YWx1ZQ==", "", 0.0))
        absent = UrlsCredentialsService(runner=lambda args: CommandResult(args, 1, "", "not found", 0.0))
        self.assertIs(present.secret_key_exists("lim-admin-credentials", "password"), True)
        self.assertIs(absent.secret_key_exists("lim-admin-credentials", "password"), False)

    def test_never_requests_the_decoded_value(self) -> None:
        # This function must only ever ask for existence via jsonpath, never
        # pipe through base64 -d or otherwise request the decoded secret.
        calls: list[tuple[str, ...]] = []

        def runner(args: tuple[str, ...]) -> CommandResult:
            calls.append(args)
            return CommandResult(args, 0, "x", "", 0.0)

        UrlsCredentialsService(runner=runner).secret_key_exists("fortify-secrets", "scancentral-client-auth-token")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("base64", " ".join(calls[0]))


class CheckAvailabilityTests(unittest.TestCase):
    def test_checks_every_known_credential_and_pairs_with_a_boolean(self) -> None:
        service = UrlsCredentialsService(runner=lambda args: CommandResult(args, 0, "present", "", 0.0))
        results = service.check_availability()
        self.assertEqual(len(results), len(CREDENTIAL_CHECKS))
        self.assertTrue(all(present for _check, present in results))

    def test_mixed_availability_reflects_per_secret_results(self) -> None:
        def runner(args: tuple[str, ...]) -> CommandResult:
            if "lim-admin-credentials" in args:
                return CommandResult(args, 1, "", "not found", 0.0)
            return CommandResult(args, 0, "present", "", 0.0)

        service = UrlsCredentialsService(runner=runner)
        results = dict((check.label, present) for check, present in service.check_availability())
        self.assertFalse(results["LIM admin password"])
        self.assertTrue(results["LIM pool password"])


if __name__ == "__main__":
    unittest.main()
