"""Local and Cloudflare R2 document object storage implementations."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any

from app.config.storage import (
    DocumentStorageSettings,
    load_document_storage_settings,
)


class DocumentStorageError(RuntimeError):
    """Base error for object storage operations."""


class DocumentNotFoundError(
    DocumentStorageError
):
    """Raised when a requested object does not exist."""


def normalize_object_key(
    key: str,
) -> str:
    """Validate and normalize an internal POSIX object key."""
    candidate = str(key).strip()

    if (
        not candidate
        or candidate.startswith("/")
        or candidate.endswith("/")
        or "\\" in candidate
        or "\x00" in candidate
    ):
        raise ValueError(
            "Invalid document object key."
        )

    path = PurePosixPath(candidate)

    if any(
        part in {
            "",
            ".",
            "..",
        }
        for part in path.parts
    ):
        raise ValueError(
            "Invalid document object key."
        )

    normalized = "/".join(
        path.parts
    )

    if normalized != candidate:
        raise ValueError(
            "Document object key is not canonical."
        )

    return normalized


class LocalDocumentStorage:
    """Store document objects below one protected local directory."""

    def __init__(
        self,
        root: str | Path,
    ):
        self.root = Path(
            root
        ).expanduser().resolve(
            strict=False
        )

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _resolve(
        self,
        key: str,
    ) -> Path:
        normalized = (
            normalize_object_key(key)
        )

        target = (
            self.root / normalized
        ).resolve(strict=False)

        if not target.is_relative_to(
            self.root
        ):
            raise ValueError(
                "Document object escaped storage root."
            )

        return target

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = (
            "application/octet-stream"
        ),
    ) -> str:
        del content_type

        if not isinstance(
            data,
            bytes,
        ):
            raise TypeError(
                "Document data must be bytes."
            )

        normalized = (
            normalize_object_key(key)
        )
        target = self._resolve(
            normalized
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = target.with_name(
            f".{target.name}.{os.getpid()}.tmp"
        )

        try:
            temporary_path.write_bytes(
                data
            )
            os.replace(
                temporary_path,
                target,
            )
        finally:
            temporary_path.unlink(
                missing_ok=True
            )

        return normalized

    def get_bytes(
        self,
        key: str,
    ) -> bytes:
        target = self._resolve(key)

        try:
            return target.read_bytes()
        except FileNotFoundError as error:
            raise DocumentNotFoundError(
                "Document object was not found."
            ) from error
        except OSError as error:
            raise DocumentStorageError(
                "Document object could not be read."
            ) from error

    def exists(
        self,
        key: str,
    ) -> bool:
        return self._resolve(
            key
        ).is_file()

    def delete(
        self,
        key: str,
    ) -> bool:
        target = self._resolve(key)

        if not target.is_file():
            return False

        try:
            target.unlink()
        except OSError as error:
            raise DocumentStorageError(
                "Document object could not be deleted."
            ) from error

        parent = target.parent

        while (
            parent != self.root
            and parent.is_relative_to(
                self.root
            )
        ):
            try:
                parent.rmdir()
            except OSError:
                break

            parent = parent.parent

        return True


def _is_not_found_error(
    error: Exception,
) -> bool:
    response = getattr(
        error,
        "response",
        None,
    )

    if not isinstance(
        response,
        dict,
    ):
        return False

    code = str(
        response.get(
            "Error",
            {},
        ).get(
            "Code",
            "",
        )
    )

    return code in {
        "404",
        "NoSuchKey",
        "NotFound",
    }


class R2DocumentStorage:
    """Store private document objects in a Cloudflare R2 bucket."""

    def __init__(
        self,
        settings: DocumentStorageSettings,
        *,
        client: Any | None = None,
    ):
        if not settings.is_r2:
            raise ValueError(
                "R2 storage requires R2 settings."
            )

        self.settings = settings
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            import boto3
            from botocore.config import (
                Config,
            )
        except ImportError as error:
            raise DocumentStorageError(
                "The boto3 dependency is unavailable."
            ) from error

        self._client = boto3.client(
            "s3",
            endpoint_url=(
                self.settings
                .r2_endpoint_url
            ),
            aws_access_key_id=(
                self.settings
                .r2_access_key_id
            ),
            aws_secret_access_key=(
                self.settings
                .r2_secret_access_key
            ),
            region_name=(
                self.settings.r2_region
            ),
            config=Config(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=30,
                retries={
                    "max_attempts": 3,
                    "mode": "standard",
                },
            ),
        )

        return self._client

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = (
            "application/octet-stream"
        ),
    ) -> str:
        if not isinstance(
            data,
            bytes,
        ):
            raise TypeError(
                "Document data must be bytes."
            )

        normalized = (
            normalize_object_key(key)
        )

        try:
            self._get_client().put_object(
                Bucket=(
                    self.settings
                    .r2_bucket_name
                ),
                Key=normalized,
                Body=data,
                ContentType=content_type,
            )
        except Exception as error:
            raise DocumentStorageError(
                "Document object could not be stored."
            ) from error

        return normalized

    def get_bytes(
        self,
        key: str,
    ) -> bytes:
        normalized = (
            normalize_object_key(key)
        )

        try:
            response = (
                self._get_client()
                .get_object(
                    Bucket=(
                        self.settings
                        .r2_bucket_name
                    ),
                    Key=normalized,
                )
            )

            body = response["Body"]

            try:
                return body.read()
            finally:
                close = getattr(
                    body,
                    "close",
                    None,
                )

                if callable(close):
                    close()

        except Exception as error:
            if _is_not_found_error(
                error
            ):
                raise (
                    DocumentNotFoundError(
                        "Document object was not found."
                    )
                ) from error

            raise DocumentStorageError(
                "Document object could not be read."
            ) from error

    def exists(
        self,
        key: str,
    ) -> bool:
        normalized = (
            normalize_object_key(key)
        )

        try:
            self._get_client().head_object(
                Bucket=(
                    self.settings
                    .r2_bucket_name
                ),
                Key=normalized,
            )
            return True
        except Exception as error:
            if _is_not_found_error(
                error
            ):
                return False

            raise DocumentStorageError(
                "Document object could not be checked."
            ) from error

    def delete(
        self,
        key: str,
    ) -> bool:
        normalized = (
            normalize_object_key(key)
        )

        existed = self.exists(
            normalized
        )

        if not existed:
            return False

        try:
            self._get_client().delete_object(
                Bucket=(
                    self.settings
                    .r2_bucket_name
                ),
                Key=normalized,
            )
        except Exception as error:
            raise DocumentStorageError(
                "Document object could not be deleted."
            ) from error

        return True


def build_document_storage(
    settings: (
        DocumentStorageSettings | None
    ) = None,
    *,
    r2_client: Any | None = None,
):
    resolved_settings = (
        settings
        or load_document_storage_settings()
    )

    if resolved_settings.is_local:
        return LocalDocumentStorage(
            resolved_settings.local_root
        )

    return R2DocumentStorage(
        resolved_settings,
        client=r2_client,
    )
