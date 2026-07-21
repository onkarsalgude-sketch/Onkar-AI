"""Configuration for automatic stuck-document recovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


DEFAULT_RECOVERY_ENABLED = True
DEFAULT_STALE_AFTER_SECONDS = 900
DEFAULT_RECOVERY_BATCH_SIZE = 25


class DocumentRecoveryConfigurationError(
    RuntimeError
):
    """Raised when recovery configuration is invalid."""


@dataclass(frozen=True)
class DocumentRecoverySettings:
    enabled: bool
    stale_after_seconds: int
    batch_size: int


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

    raise DocumentRecoveryConfigurationError(
        f"{name} must be a boolean value."
    )


def _parse_integer(
    name: str,
    raw_value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if raw_value is None:
        return default

    normalized = str(
        raw_value
    ).strip()

    if not normalized:
        return default

    try:
        value = int(normalized)
    except ValueError as error:
        raise DocumentRecoveryConfigurationError(
            f"{name} must be an integer."
        ) from error

    if value < minimum or value > maximum:
        raise DocumentRecoveryConfigurationError(
            f"{name} must be between "
            f"{minimum} and {maximum}."
        )

    return value


def load_document_recovery_settings(
    environ: Mapping[str, str] | None = None,
) -> DocumentRecoverySettings:
    source = (
        os.environ
        if environ is None
        else environ
    )

    return DocumentRecoverySettings(
        enabled=_parse_boolean(
            "DOCUMENT_RECOVERY_ENABLED",
            source.get(
                "DOCUMENT_RECOVERY_ENABLED"
            ),
            default=DEFAULT_RECOVERY_ENABLED,
        ),
        stale_after_seconds=_parse_integer(
            "DOCUMENT_RECOVERY_STALE_SECONDS",
            source.get(
                "DOCUMENT_RECOVERY_STALE_SECONDS"
            ),
            default=(
                DEFAULT_STALE_AFTER_SECONDS
            ),
            minimum=60,
            maximum=604800,
        ),
        batch_size=_parse_integer(
            "DOCUMENT_RECOVERY_BATCH_SIZE",
            source.get(
                "DOCUMENT_RECOVERY_BATCH_SIZE"
            ),
            default=(
                DEFAULT_RECOVERY_BATCH_SIZE
            ),
            minimum=1,
            maximum=100,
        ),
    )
