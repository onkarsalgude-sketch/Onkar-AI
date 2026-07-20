"""Configuration for local and durable document object storage."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


class DocumentStorageConfigurationError(RuntimeError):
    """Raised when document storage settings are unsafe or incomplete."""


@dataclass(frozen=True)
class DocumentStorageSettings:
    backend: str
    require_persistence: bool
    local_root: Path
    r2_endpoint_url: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    r2_region: str

    @property
    def is_local(self) -> bool:
        return self.backend == "local"

    @property
    def is_r2(self) -> bool:
        return self.backend == "r2"

    @property
    def safe_target(self) -> str:
        if self.is_local:
            return f"local:///{self.local_root}"

        parsed = urlparse(
            self.r2_endpoint_url
        )

        return (
            f"r2://{self.r2_bucket_name}"
            f"@{parsed.hostname or 'unknown'}"
        )


def _parse_bool(value: object) -> bool:
    normalized = str(
        value
    ).strip().casefold()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "",
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise DocumentStorageConfigurationError(
        "Invalid document storage boolean setting."
    )


def _default_local_root() -> Path:
    project_root = (
        Path(__file__).resolve().parents[2]
    )

    return (
        project_root
        / "storage"
        / "uploads"
    )


def _validate_r2_endpoint(
    endpoint_url: str,
) -> str:
    normalized = endpoint_url.rstrip(
        "/"
    )

    parsed = urlparse(normalized)

    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise (
            DocumentStorageConfigurationError(
                "R2 endpoint URL is invalid."
            )
        )

    return normalized


def load_document_storage_settings(
    environ: Mapping[str, str] | None = None,
    *,
    default_local_root: str | Path | None = None,
) -> DocumentStorageSettings:
    """Load local or Cloudflare R2 document storage settings."""
    source = (
        os.environ
        if environ is None
        else environ
    )

    backend = str(
        source.get(
            "DOCUMENT_STORAGE_BACKEND",
            "local",
        )
    ).strip().casefold()

    if backend not in {
        "local",
        "r2",
    }:
        raise (
            DocumentStorageConfigurationError(
                "Unsupported document storage backend."
            )
        )

    require_persistence = _parse_bool(
        source.get(
            "DOCUMENT_STORAGE_REQUIRE_PERSISTENCE",
            "false",
        )
    )

    configured_local_root = str(
        source.get(
            "DOCUMENT_STORAGE_LOCAL_ROOT",
            "",
        )
    ).strip()

    fallback_root = (
        Path(default_local_root)
        if default_local_root is not None
        else _default_local_root()
    )

    local_root = (
        Path(
            configured_local_root
        ).expanduser()
        if configured_local_root
        else fallback_root
    ).resolve(strict=False)

    endpoint_url = str(
        source.get(
            "R2_ENDPOINT_URL",
            "",
        )
    ).strip()

    access_key_id = str(
        source.get(
            "R2_ACCESS_KEY_ID",
            "",
        )
    ).strip()

    secret_access_key = str(
        source.get(
            "R2_SECRET_ACCESS_KEY",
            "",
        )
    ).strip()

    bucket_name = str(
        source.get(
            "R2_BUCKET_NAME",
            "",
        )
    ).strip()

    region = str(
        source.get(
            "R2_REGION",
            "auto",
        )
    ).strip() or "auto"

    if (
        require_persistence
        and backend == "local"
    ):
        raise (
            DocumentStorageConfigurationError(
                "Durable document storage is required."
            )
        )

    if backend == "r2":
        endpoint_url = (
            _validate_r2_endpoint(
                endpoint_url
            )
        )

        if (
            not access_key_id
            or not secret_access_key
            or not bucket_name
        ):
            raise (
                DocumentStorageConfigurationError(
                    "R2 credentials or bucket are missing."
                )
            )

        if (
            any(
                character.isspace()
                for character in bucket_name
            )
            or "/" in bucket_name
            or "\\" in bucket_name
        ):
            raise (
                DocumentStorageConfigurationError(
                    "R2 bucket name is invalid."
                )
            )

    return DocumentStorageSettings(
        backend=backend,
        require_persistence=(
            require_persistence
        ),
        local_root=local_root,
        r2_endpoint_url=endpoint_url,
        r2_access_key_id=access_key_id,
        r2_secret_access_key=(
            secret_access_key
        ),
        r2_bucket_name=bucket_name,
        r2_region=region,
    )
