"""Secure, default-disabled configuration for system-incident alerts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit


DEFAULT_SYSTEM_INCIDENT_ALERTS_ENABLED = False
DEFAULT_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS = 5.0
MIN_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS = 0.5
MAX_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS = 30.0

DEFAULT_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS = 300.0
MIN_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS = 1.0
MAX_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS = 86400.0
MAX_SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL_LENGTH = 2048

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


class SystemIncidentAlertingConfigurationError(
    RuntimeError
):
    """Raised when outbound incident-alert settings are unsafe."""


@dataclass(
    frozen=True
)
class SystemIncidentAlertingSettings:
    """Runtime settings for one generic HTTPS webhook provider."""

    enabled: bool = (
        DEFAULT_SYSTEM_INCIDENT_ALERTS_ENABLED
    )

    webhook_url: str = field(
        default="",
        repr=False,
    )

    timeout_seconds: float = (
        DEFAULT_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS
    )

    stale_after_seconds: float = (
        DEFAULT_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS
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
            "webhook_url",
            str(
                self.webhook_url
            ).strip(),
        )

        if isinstance(
            self.timeout_seconds,
            bool,
        ):
            raise SystemIncidentAlertingConfigurationError(
                "SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS "
                "must be numeric."
            )

        try:
            normalized_timeout = float(
                self.timeout_seconds
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise SystemIncidentAlertingConfigurationError(
                "SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS "
                "must be numeric."
            ) from error

        object.__setattr__(
            self,
            "timeout_seconds",
            normalized_timeout,
        )

        if isinstance(
            self.stale_after_seconds,
            bool,
        ):
            raise SystemIncidentAlertingConfigurationError(
                "SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS "
                "must be numeric."
            )

        try:
            normalized_stale_after = float(
                self.stale_after_seconds
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise SystemIncidentAlertingConfigurationError(
                "SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS "
                "must be numeric."
            ) from error

        object.__setattr__(
            self,
            "stale_after_seconds",
            normalized_stale_after,
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

    raise SystemIncidentAlertingConfigurationError(
        f"{name} must be a valid boolean value."
    )


def _validate_webhook_url(
    webhook_url: str,
) -> None:
    if (
        not webhook_url
        or len(
            webhook_url
        )
        > MAX_SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL_LENGTH
    ):
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL "
            "must be a valid HTTPS URL."
        )

    if any(
        character.isspace()
        or ord(
            character
        ) < 32
        for character in webhook_url
    ):
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL "
            "must be a valid HTTPS URL."
        )

    try:
        parsed = urlsplit(
            webhook_url
        )

        port = parsed.port
    except ValueError as error:
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL "
            "must be a valid HTTPS URL."
        ) from error

    del port

    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(
            parsed.fragment
        )
    ):
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL "
            "must be a valid HTTPS URL."
        )


def validate_system_incident_alerting_settings(
    settings: SystemIncidentAlertingSettings,
) -> None:
    """Fail closed for unsafe webhook, timeout, and recovery configuration."""
    if not isinstance(
        settings,
        SystemIncidentAlertingSettings,
    ):
        raise SystemIncidentAlertingConfigurationError(
            "System incident alerting settings are invalid."
        )

    if not (
        MIN_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS
        <= settings.timeout_seconds
        <= MAX_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS
    ):
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS "
            "must be between 0.5 and 30 seconds."
        )

    if not (
        MIN_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS
        <= settings.stale_after_seconds
        <= MAX_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS
    ):
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS "
            "must be between 1 and 86400 seconds."
        )

    if settings.webhook_url:
        _validate_webhook_url(
            settings.webhook_url
        )

    if (
        settings.enabled
        and not settings.webhook_url
    ):
        raise SystemIncidentAlertingConfigurationError(
            "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL "
            "is required when incident alerts are enabled."
        )


def load_system_incident_alerting_settings(
    environ: Mapping[
        str,
        str,
    ] | None = None,
) -> SystemIncidentAlertingSettings:
    """Load default-disabled outbound incident-alert settings."""
    source = (
        os.environ
        if environ is None
        else environ
    )

    enabled = _parse_boolean(
        source.get(
            "SYSTEM_INCIDENT_ALERTS_ENABLED"
        ),
        name=(
            "SYSTEM_INCIDENT_ALERTS_ENABLED"
        ),
        default=(
            DEFAULT_SYSTEM_INCIDENT_ALERTS_ENABLED
        ),
    )

    settings = SystemIncidentAlertingSettings(
        enabled=enabled,
        webhook_url=str(
            source.get(
                "SYSTEM_INCIDENT_ALERTS_WEBHOOK_URL",
                "",
            )
        ),
        timeout_seconds=source.get(
            "SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS",
            str(
                DEFAULT_SYSTEM_INCIDENT_ALERTS_TIMEOUT_SECONDS
            ),
        ),
        stale_after_seconds=source.get(
            "SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS",
            str(
                DEFAULT_SYSTEM_INCIDENT_ALERTS_STALE_AFTER_SECONDS
            ),
        ),
    )

    validate_system_incident_alerting_settings(
        settings
    )

    return settings
