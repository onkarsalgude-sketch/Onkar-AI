"""Configuration for the secure system-health monitoring API."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field


DEFAULT_SYSTEM_HEALTH_STATUS_ENABLED = False

_SYSTEM_HEALTH_DIGEST_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)

_TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}

_FALSE_VALUES = {
    "0",
    "false",
    "no",
    "off",
}


class SystemHealthMonitoringConfigurationError(
    RuntimeError
):
    """Raised when system-health monitoring configuration is invalid."""


@dataclass(
    frozen=True,
    slots=True,
)
class SystemHealthMonitoringSettings:
    """Secure runtime settings for the system-health endpoint."""

    enabled: bool = (
        DEFAULT_SYSTEM_HEALTH_STATUS_ENABLED
    )

    token_sha256: str = field(
        default="",
        repr=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "enabled",
            bool(
                self.enabled
            ),
        )

        object.__setattr__(
            self,
            "token_sha256",
            str(
                self.token_sha256
            ).strip().casefold(),
        )


def _parse_boolean(
    value: object,
    *,
    name: str,
    default: bool,
) -> bool:
    if value is None:
        return default

    normalized = str(
        value
    ).strip().casefold()

    if normalized in _TRUE_VALUES:
        return True

    if normalized in _FALSE_VALUES:
        return False

    raise SystemHealthMonitoringConfigurationError(
        f"{name} must be a valid boolean value."
    )


def validate_system_health_monitoring_settings(
    settings: SystemHealthMonitoringSettings,
) -> None:
    """Fail closed for missing or malformed monitoring credentials."""

    digest = str(
        settings.token_sha256
    ).strip().casefold()

    if (
        digest
        and not _SYSTEM_HEALTH_DIGEST_PATTERN.fullmatch(
            digest
        )
    ):
        raise SystemHealthMonitoringConfigurationError(
            "SYSTEM_HEALTH_STATUS_TOKEN_SHA256 "
            "must be a 64-character SHA-256 digest."
        )

    if (
        settings.enabled
        and not digest
    ):
        raise SystemHealthMonitoringConfigurationError(
            "SYSTEM_HEALTH_STATUS_TOKEN_SHA256 "
            "is required when system-health monitoring "
            "is enabled."
        )


def load_system_health_monitoring_settings(
    environ: Mapping[
        str,
        str,
    ] | None = None,
) -> SystemHealthMonitoringSettings:
    """Load default-disabled system-health monitoring settings."""

    source = (
        os.environ
        if environ is None
        else environ
    )

    enabled = _parse_boolean(
        source.get(
            "SYSTEM_HEALTH_STATUS_ENABLED"
        ),
        name="SYSTEM_HEALTH_STATUS_ENABLED",
        default=(
            DEFAULT_SYSTEM_HEALTH_STATUS_ENABLED
        ),
    )

    settings = SystemHealthMonitoringSettings(
        enabled=enabled,
        token_sha256=str(
            source.get(
                "SYSTEM_HEALTH_STATUS_TOKEN_SHA256",
                "",
            )
        ),
    )

    validate_system_health_monitoring_settings(
        settings
    )

    return settings
