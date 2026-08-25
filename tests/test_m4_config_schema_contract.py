from __future__ import annotations

import unittest

from fortifylab.config import (
    CONFIG_SECTIONS,
    DERIVED_URL_REPAIRS,
    M4_CONFIG_CONTRACT,
    EnvDocumentCapability,
    field_by_key,
    fields_for_section,
    is_secret_key,
    redacted_value,
)


class ConfigSchemaContractTests(unittest.TestCase):
    def test_contract_requires_non_destructive_parser_writer_behaviors(self) -> None:
        capabilities = set(M4_CONFIG_CONTRACT.capabilities)

        self.assertIn(EnvDocumentCapability.PRESERVE_COMMENTS, capabilities)
        self.assertIn(EnvDocumentCapability.PRESERVE_ORDER, capabilities)
        self.assertIn(EnvDocumentCapability.BACKUP_BEFORE_WRITE, capabilities)
        self.assertIn(EnvDocumentCapability.DRY_RUN_DIFFS, capabilities)
        self.assertIn(EnvDocumentCapability.REDACT_SECRETS_IN_DIFFS, capabilities)
        self.assertEqual(M4_CONFIG_CONTRACT.deprecated_bridge, "src/fortifylab/config")

    def test_sections_keep_current_configuration_editor_shape(self) -> None:
        section_ids = {section.id for section in CONFIG_SECTIONS}

        self.assertIn("identity", section_ids)
        self.assertIn("domain_urls", section_ids)
        self.assertIn("versions", section_ids)
        self.assertIn("credentials", section_ids)
        self.assertIn("tls", section_ids)

    def test_domain_url_repair_contract_matches_existing_wizard_scope(self) -> None:
        repairs = {repair.key: repair.expression for repair in DERIVED_URL_REPAIRS}

        self.assertEqual(repairs["SSC"], "ssc.$DOMAIN")
        self.assertEqual(repairs["LIM_API_URL"], "https://$LIM/LIM.API")
        self.assertEqual(repairs["SCSAST_CTRL_URL"], "https://$SCSAST/scancentral-ctrl/")

    def test_secret_detection_covers_named_fields_and_sensitive_patterns(self) -> None:
        self.assertTrue(is_secret_key("DEFAULT_PASS"))
        self.assertTrue(is_secret_key("FORTIFY_BYO_TLS_KEY"))
        self.assertTrue(is_secret_key("SOME_RUNTIME_TOKEN"))
        self.assertFalse(is_secret_key("SSC_URL"))
        self.assertEqual(redacted_value("DEFAULT_PASS", "changeme"), "<redacted>")
        self.assertEqual(redacted_value("SSC_URL", "https://ssc.example.test"), "https://ssc.example.test")

    def test_field_lookup_is_read_only_metadata(self) -> None:
        field = field_by_key("FORTIFY_TLS_MODE")
        self.assertIsNotNone(field)
        assert field is not None
        self.assertEqual(field.choices, ("mkcert", "byo"))

        keys = tuple(field.key for field in fields_for_section("domain_urls"))
        self.assertIn("DOMAIN", keys)
        self.assertIn("SSC_URL", keys)


if __name__ == "__main__":
    unittest.main()
