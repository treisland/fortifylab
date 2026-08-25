"""Read-only configuration schema contracts for the Python TUI migration.

This module intentionally does not parse, write, or validate a live ``.env``
file yet. M4 implementation can build against these contracts after M3
operation boundaries are settled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class ConfigFieldKind(str, Enum):
    """High-level editor behavior for a Fortify Lab ``.env`` field."""

    TEXT = "text"
    SECRET = "secret"
    PATH = "path"
    URL = "url"
    HOSTNAME = "hostname"
    VERSION = "version"
    ENUM = "enum"
    LIST = "list"


class EnvDocumentCapability(str, Enum):
    """Parser/writer guarantees required before replacing Bash config editing."""

    PRESERVE_COMMENTS = "preserve_comments"
    PRESERVE_ORDER = "preserve_order"
    PRESERVE_EXPORT_PREFIX = "preserve_export_prefix"
    PRESERVE_EXPRESSIONS = "preserve_expressions"
    BACKUP_BEFORE_WRITE = "backup_before_write"
    ROLLBACK_MARKER = "rollback_marker"
    REDACT_SECRETS_IN_DIFFS = "redact_secrets_in_diffs"
    VALIDATE_BEFORE_MUTATION = "validate_before_mutation"
    DRY_RUN_DIFFS = "dry_run_diffs"


@dataclass(frozen=True)
class ConfigField:
    """One managed field in the future Python config editor."""

    key: str
    section: str
    kind: ConfigFieldKind = ConfigFieldKind.TEXT
    default: str | None = None
    choices: tuple[str, ...] = ()
    derived: bool = False
    secret: bool = False
    required: bool = False
    note: str = ""


@dataclass(frozen=True)
class ConfigSection:
    """A TUI section that preserves the current Bash editor navigation."""

    id: str
    title: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class DerivedValue:
    """A deterministic repair value derived from ``DOMAIN``."""

    key: str
    expression: str


@dataclass(frozen=True)
class ParserWriterContract:
    """Non-mutating contract that M4 parser/writer implementation must satisfy."""

    capabilities: tuple[EnvDocumentCapability, ...]
    backup_directory: str = ".env.backups"
    rollback_marker: str = ".env.rollback"
    source_of_truth: str = ".env.example"
    deprecated_bridge: str = "src/fortifylab/config"


SECRET_KEY_RE = re.compile(r"(PASS|PASSWORD|TOKEN|SECRET|KEY|LICENSE|CREDENTIAL)", re.IGNORECASE)


DERIVED_URL_REPAIRS: tuple[DerivedValue, ...] = (
    DerivedValue("DOMAIN", "{domain}"),
    DerivedValue("SSC", "ssc.$DOMAIN"),
    DerivedValue("LIM", "lim.$DOMAIN"),
    DerivedValue("SCDAST", "dast.$DOMAIN"),
    DerivedValue("SCSAST", "sast.$DOMAIN"),
    DerivedValue("SSC_URL", "https://$SSC"),
    DerivedValue("LIM_URL", "https://$LIM"),
    DerivedValue("LIM_API_URL", "https://$LIM/LIM.API"),
    DerivedValue("SCDAST_URL", "https://$SCDAST"),
    DerivedValue("SCSAST_URL", "https://$SCSAST"),
    DerivedValue("SCSAST_CTRL_URL", "https://$SCSAST/scancentral-ctrl/"),
)


CONFIG_SECTIONS: tuple[ConfigSection, ...] = (
    ConfigSection("identity", "Kubernetes namespace", ("NAMESPACE", "FORTIFY_DEPLOYMENT_PROFILE", "FORTIFY_DEPLOYMENT_COMPONENTS")),
    ConfigSection(
        "domain_urls",
        "Lab domain and derived URLs",
        ("DOMAIN", "SSC", "LIM", "SCDAST", "SCSAST", "SSC_URL", "LIM_URL", "LIM_API_URL", "SCDAST_URL", "SCSAST_URL", "SCSAST_CTRL_URL"),
    ),
    ConfigSection(
        "versions",
        "Deployment versions and Flight Plans",
        (
            "FORTIFY_FLIGHT_PLAN",
            "FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS",
            "FORTIFY_SSC_CHART_VERSION",
            "FORTIFY_SSC_IMAGE_TAG",
            "FORTIFY_SCSAST_CHART_VERSION",
            "FORTIFY_SCSAST_CTRL_IMAGE_TAG",
            "FORTIFY_SCSAST_WORKER_IMAGE_TAG",
            "FORTIFY_SCDAST_CHART_VERSION",
            "FORTIFY_LIM_CHART_VERSION",
            "FORTIFY_MYSQL_CHART_VERSION",
            "FORTIFY_POSTGRES_CHART_VERSION",
            "FORTIFY_POSTGRES_IMAGE_TAG",
            "FORTIFY_MYSQL_IMAGE_TAG",
            "FORTIFY_RECOMMENDED_FCLI_VERSION",
        ),
    ),
    ConfigSection(
        "credentials",
        "Credentials, users, and passwords",
        (
            "DEFAULT_PASS",
            "DEFAULT_ALIAS",
            "SCDAST_SSC_USER",
            "SCDAST_SSC_PASS",
            "SCDAST_DB_OWNER_USER",
            "SCDAST_DB_OWNER_PASS",
            "SCDAST_DB_STANDARD_USER",
            "SCDAST_DB_STANDARD_PASS",
            "LIM_POOL_NAME",
            "LIM_POOL_PASS",
            "FORTIFY_LICENSE_FILE",
        ),
    ),
    ConfigSection(
        "tls",
        "Certificates and trust",
        ("FORTIFY_TLS_MODE", "FORTIFY_BYO_TLS_CERT", "FORTIFY_BYO_TLS_KEY", "FORTIFY_BYO_TLS_CA_CERT", "FORTIFY_CERTS", "TRUSTSTORE", "FCLI_CLIENT_TRUSTSTORE"),
    ),
    ConfigSection(
        "sample_apps",
        "Sample applications",
        ("JUICE_SHOP", "WEBGOAT", "DVWA", "JUICE_SHOP_URL", "WEBGOAT_URL", "DVWA_URL", "FORTIFY_SAMPLE_JUICE_SHOP_IMAGE", "FORTIFY_SAMPLE_WEBGOAT_IMAGE", "FORTIFY_SAMPLE_DVWA_IMAGE"),
    ),
)


CONFIG_FIELDS: tuple[ConfigField, ...] = (
    ConfigField("NAMESPACE", "identity", default="fortify", required=True),
    ConfigField("FORTIFY_DEPLOYMENT_PROFILE", "identity", ConfigFieldKind.ENUM, "full_lab", ("full_lab", "ssc_only", "sast_standalone", "sast_full", "dast_full", "custom")),
    ConfigField("FORTIFY_DEPLOYMENT_COMPONENTS", "identity", ConfigFieldKind.LIST),
    ConfigField("DOMAIN", "domain_urls", ConfigFieldKind.HOSTNAME, default="fortifydemo.com", required=True),
    ConfigField("SSC", "domain_urls", ConfigFieldKind.HOSTNAME, "ssc.$DOMAIN", derived=True, required=True),
    ConfigField("LIM", "domain_urls", ConfigFieldKind.HOSTNAME, "lim.$DOMAIN", derived=True, required=True),
    ConfigField("SCDAST", "domain_urls", ConfigFieldKind.HOSTNAME, "dast.$DOMAIN", derived=True, required=True),
    ConfigField("SCSAST", "domain_urls", ConfigFieldKind.HOSTNAME, "sast.$DOMAIN", derived=True, required=True),
    ConfigField("SSC_URL", "domain_urls", ConfigFieldKind.URL, "https://$SSC", derived=True, required=True),
    ConfigField("LIM_URL", "domain_urls", ConfigFieldKind.URL, "https://$LIM", derived=True, required=True),
    ConfigField("LIM_API_URL", "domain_urls", ConfigFieldKind.URL, "https://$LIM/LIM.API", derived=True, required=True),
    ConfigField("SCDAST_URL", "domain_urls", ConfigFieldKind.URL, "https://$SCDAST", derived=True, required=True),
    ConfigField("SCSAST_URL", "domain_urls", ConfigFieldKind.URL, "https://$SCSAST", derived=True, required=True),
    ConfigField("SCSAST_CTRL_URL", "domain_urls", ConfigFieldKind.URL, "https://$SCSAST/scancentral-ctrl/", derived=True, required=True),
    ConfigField("FORTIFY_FLIGHT_PLAN", "versions", ConfigFieldKind.ENUM, "fortify-26.2"),
    ConfigField("FORTIFY_FLIGHT_PLAN_DRIFT_COMPONENTS", "versions", ConfigFieldKind.LIST),
    ConfigField("FORTIFY_SSC_CHART_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_SSC_IMAGE_TAG", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_SCSAST_CHART_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_SCSAST_CTRL_IMAGE_TAG", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_SCSAST_WORKER_IMAGE_TAG", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_SCDAST_CHART_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_LIM_CHART_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_MYSQL_CHART_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_POSTGRES_CHART_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_POSTGRES_IMAGE_TAG", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_MYSQL_IMAGE_TAG", "versions", ConfigFieldKind.VERSION),
    ConfigField("FORTIFY_RECOMMENDED_FCLI_VERSION", "versions", ConfigFieldKind.VERSION),
    ConfigField("DEFAULT_PASS", "credentials", ConfigFieldKind.SECRET, secret=True, required=True),
    ConfigField("DEFAULT_ALIAS", "credentials"),
    ConfigField("SCDAST_SSC_USER", "credentials"),
    ConfigField("SCDAST_SSC_PASS", "credentials", ConfigFieldKind.SECRET, secret=True),
    ConfigField("SCDAST_DB_OWNER_USER", "credentials"),
    ConfigField("SCDAST_DB_OWNER_PASS", "credentials", ConfigFieldKind.SECRET, secret=True),
    ConfigField("SCDAST_DB_STANDARD_USER", "credentials"),
    ConfigField("SCDAST_DB_STANDARD_PASS", "credentials", ConfigFieldKind.SECRET, secret=True),
    ConfigField("LIM_POOL_NAME", "credentials"),
    ConfigField("LIM_POOL_PASS", "credentials", ConfigFieldKind.SECRET, secret=True),
    ConfigField("FORTIFY_LICENSE_FILE", "credentials", ConfigFieldKind.PATH, secret=True, required=True),
    ConfigField("FORTIFY_TLS_MODE", "tls", ConfigFieldKind.ENUM, "mkcert", ("mkcert", "byo"), required=True),
    ConfigField("FORTIFY_BYO_TLS_CERT", "tls", ConfigFieldKind.PATH),
    ConfigField("FORTIFY_BYO_TLS_KEY", "tls", ConfigFieldKind.PATH, secret=True),
    ConfigField("FORTIFY_BYO_TLS_CA_CERT", "tls", ConfigFieldKind.PATH),
    ConfigField("FORTIFY_CERTS", "tls", ConfigFieldKind.PATH),
    ConfigField("TRUSTSTORE", "tls", ConfigFieldKind.PATH, secret=True),
    ConfigField("FCLI_CLIENT_TRUSTSTORE", "tls", ConfigFieldKind.PATH, secret=True),
    ConfigField("JUICE_SHOP", "sample_apps", ConfigFieldKind.HOSTNAME, "juice-shop.$DOMAIN", derived=True),
    ConfigField("WEBGOAT", "sample_apps", ConfigFieldKind.HOSTNAME, "webgoat.$DOMAIN", derived=True),
    ConfigField("DVWA", "sample_apps", ConfigFieldKind.HOSTNAME, "dvwa.$DOMAIN", derived=True),
    ConfigField("JUICE_SHOP_URL", "sample_apps", ConfigFieldKind.URL, "https://$JUICE_SHOP", derived=True),
    ConfigField("WEBGOAT_URL", "sample_apps", ConfigFieldKind.URL, "https://$WEBGOAT", derived=True),
    ConfigField("DVWA_URL", "sample_apps", ConfigFieldKind.URL, "https://$DVWA", derived=True),
    ConfigField("FORTIFY_SAMPLE_JUICE_SHOP_IMAGE", "sample_apps"),
    ConfigField("FORTIFY_SAMPLE_WEBGOAT_IMAGE", "sample_apps"),
    ConfigField("FORTIFY_SAMPLE_DVWA_IMAGE", "sample_apps"),
)


M4_CONFIG_CONTRACT = ParserWriterContract(
    capabilities=(
        EnvDocumentCapability.PRESERVE_COMMENTS,
        EnvDocumentCapability.PRESERVE_ORDER,
        EnvDocumentCapability.PRESERVE_EXPORT_PREFIX,
        EnvDocumentCapability.PRESERVE_EXPRESSIONS,
        EnvDocumentCapability.BACKUP_BEFORE_WRITE,
        EnvDocumentCapability.ROLLBACK_MARKER,
        EnvDocumentCapability.REDACT_SECRETS_IN_DIFFS,
        EnvDocumentCapability.VALIDATE_BEFORE_MUTATION,
        EnvDocumentCapability.DRY_RUN_DIFFS,
    )
)


def field_by_key(key: str) -> ConfigField | None:
    """Return schema metadata for ``key`` without touching a live environment."""

    return next((field for field in CONFIG_FIELDS if field.key == key), None)


def fields_for_section(section_id: str) -> tuple[ConfigField, ...]:
    """Return managed fields for a future TUI config section."""

    keys = next((section.keys for section in CONFIG_SECTIONS if section.id == section_id), ())
    return tuple(field for key in keys if (field := field_by_key(key)) is not None)


def is_secret_key(key: str) -> bool:
    """Return whether ``key`` should be redacted in previews, logs, and diffs."""

    field = field_by_key(key)
    return bool(field and field.secret) or bool(SECRET_KEY_RE.search(key))


def redacted_value(key: str, value: str | None) -> str:
    """Render a value for diagnostics or diffs without exposing secrets."""

    if value in (None, ""):
        return "<unset>"
    if is_secret_key(key):
        return "<redacted>"
    return value
