"""Configuration for the document recovery status endpoint."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping


DEFAULT_DOCUMENT_RECOVERY_STATUS_ENABLED = False

_SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


class DocumentRecoveryMonitoringConfigurationError(
    RuntimeError
):
    """Raised when recovery monitoring configuration is invalid."""


@dataclass(frozen=True)
class DocumentRecoveryMonitoringSettings:
    enabled: bool
    token_sha256: str


def _parse_boolean(
    name: str,
    raw_value: str | None,
    *,
    default: bool,
) -> bool:
    if raw_value is None:
        return default

    normalized = str(
        raw_value
    ).strip().casefold()

    if not normalized:
        return default

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise DocumentRecoveryMonitoringConfigurationError(
        f"{name} must be a boolean value."
    )


def validate_document_recovery_monitoring_settings(
    settings: DocumentRecoveryMonitoringSettings,
) -> None:
    token_sha256 = str(
        settings.token_sha256
    ).strip().casefold()

    if token_sha256 and not _SHA256_PATTERN.fullmatch(
        token_sha256
    ):
        raise DocumentRecoveryMonitoringConfigurationError(
            "DOCUMENT_RECOVERY_STATUS_TOKEN_SHA256 "
            "must contain exactly 64 hexadecimal characters."
        )

    if settings.enabled and not token_sha256:
        raise DocumentRecoveryMonitoringConfigurationError(
            "DOCUMENT_RECOVERY_STATUS_TOKEN_SHA256 "
            "is required when recovery monitoring is enabled."
        )


def load_document_recovery_monitoring_settings(
    environ: Mapping[str, str] | None = None,
) -> DocumentRecoveryMonitoringSettings:
    source = (
        os.environ
        if environ is None
        else environ
    )

    settings = DocumentRecoveryMonitoringSettings(
        enabled=_parse_boolean(
            "DOCUMENT_RECOVERY_STATUS_ENABLED",
            source.get(
                "DOCUMENT_RECOVERY_STATUS_ENABLED"
            ),
            default=(
                DEFAULT_DOCUMENT_RECOVERY_STATUS_ENABLED
            ),
        ),
        token_sha256=str(
            source.get(
                "DOCUMENT_RECOVERY_STATUS_TOKEN_SHA256",
                "",
            )
        ).strip().casefold(),
    )

    validate_document_recovery_monitoring_settings(
        settings
    )

    return settings
