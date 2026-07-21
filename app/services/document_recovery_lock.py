"""Cross-process lock for startup document recovery."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from app.config.database import (
    DatabaseSettings,
    load_database_settings,
)
from app.database.db import (
    get_runtime_connection,
)


DOCUMENT_RECOVERY_ADVISORY_LOCK_ID = 752029


def _no_op_release() -> None:
    return None


def _safe_rollback(
    connection: Any,
) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _safe_close(
    connection: Any,
) -> None:
    try:
        connection.close()
    except Exception:
        pass


def _safe_invalidate(
    connection: Any,
) -> None:
    try:
        invalidate = getattr(
            connection,
            "invalidate",
            None,
        )

        if callable(invalidate):
            invalidate()
            return
    except Exception:
        pass

    _safe_close(
        connection
    )


def _first_row_value(
    row: Any,
) -> Any:
    if row is None:
        raise RuntimeError(
            "Document recovery lock query returned no row."
        )

    mapping = getattr(
        row,
        "_mapping",
        None,
    )

    if mapping is not None:
        values = tuple(
            mapping.values()
        )

        if not values:
            raise RuntimeError(
                "Document recovery lock query returned "
                "an empty row."
            )

        return values[0]

    if isinstance(
        row,
        Mapping,
    ):
        values = tuple(
            row.values()
        )

        if not values:
            raise RuntimeError(
                "Document recovery lock query returned "
                "an empty mapping."
            )

        return values[0]

    try:
        return row[0]
    except (
        IndexError,
        KeyError,
        TypeError,
    ) as error:
        raise RuntimeError(
            "Document recovery lock query returned "
            "an unsupported row."
        ) from error


@dataclass
class DocumentRecoveryLockLease:
    acquired: bool
    backend: str
    _release_callback: Callable[[], None] = field(
        repr=False,
        compare=False,
    )
    _released: bool = field(
        default=False,
        init=False,
        repr=False,
        compare=False,
    )

    def release(self) -> None:
        if self._released:
            return

        self._released = True
        self._release_callback()

    def __enter__(
        self,
    ) -> "DocumentRecoveryLockLease":
        return self

    def __exit__(
        self,
        exception_type,
        exception,
        traceback,
    ) -> bool:
        self.release()
        return False


def _sqlite_lock_path(
    settings: DatabaseSettings,
) -> Path:
    return Path(
        str(settings.sqlite_path)
        + ".document-recovery.lock"
    )


def _try_acquire_sqlite_lock(
    settings: DatabaseSettings,
    *,
    file_lock_factory: Callable = FileLock,
) -> DocumentRecoveryLockLease:
    lock_path = _sqlite_lock_path(
        settings
    )

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_lock = file_lock_factory(
        str(lock_path),
        timeout=0,
        thread_local=False,
    )

    try:
        file_lock.acquire(
            timeout=0,
            blocking=False,
        )
    except FileLockTimeout:
        return DocumentRecoveryLockLease(
            acquired=False,
            backend="sqlite",
            _release_callback=_no_op_release,
        )

    def release_sqlite_lock() -> None:
        try:
            file_lock.release()
        except Exception:
            pass

    return DocumentRecoveryLockLease(
        acquired=True,
        backend="sqlite",
        _release_callback=release_sqlite_lock,
    )


def _try_acquire_postgresql_lock(
    *,
    db_path: str | None,
    environ: Mapping[str, str] | None,
    connection_factory: Callable,
) -> DocumentRecoveryLockLease:
    connection = connection_factory(
        db_path,
        environ=environ,
    )

    try:
        cursor = connection.execute(
            "SELECT pg_try_advisory_lock(?)",
            (
                DOCUMENT_RECOVERY_ADVISORY_LOCK_ID,
            ),
        )

        acquired = bool(
            _first_row_value(
                cursor.fetchone()
            )
        )

        connection.commit()
    except Exception:
        _safe_rollback(
            connection
        )
        _safe_close(
            connection
        )
        raise

    if not acquired:
        _safe_close(
            connection
        )

        return DocumentRecoveryLockLease(
            acquired=False,
            backend="postgresql",
            _release_callback=_no_op_release,
        )

    def release_postgresql_lock() -> None:
        try:
            cursor = connection.execute(
                "SELECT pg_advisory_unlock(?)",
                (
                    DOCUMENT_RECOVERY_ADVISORY_LOCK_ID,
                ),
            )

            unlocked = bool(
                _first_row_value(
                    cursor.fetchone()
                )
            )

            if not unlocked:
                raise RuntimeError(
                    "PostgreSQL document recovery "
                    "lock was not released."
                )

            connection.commit()
        except Exception:
            _safe_rollback(
                connection
            )

            _safe_invalidate(
                connection
            )

            return

        _safe_close(
            connection
        )

    return DocumentRecoveryLockLease(
        acquired=True,
        backend="postgresql",
        _release_callback=release_postgresql_lock,
    )


def try_acquire_document_recovery_lock(
    *,
    db_path: str | None = None,
    environ: Mapping[str, str] | None = None,
    settings_loader: Callable = (
        load_database_settings
    ),
    connection_factory: Callable = (
        get_runtime_connection
    ),
    file_lock_factory: Callable = FileLock,
) -> DocumentRecoveryLockLease:
    settings = settings_loader(
        environ,
        default_sqlite_path=db_path,
    )

    if settings.is_sqlite:
        return _try_acquire_sqlite_lock(
            settings,
            file_lock_factory=(
                file_lock_factory
            ),
        )

    if settings.is_postgresql:
        return _try_acquire_postgresql_lock(
            db_path=db_path,
            environ=environ,
            connection_factory=(
                connection_factory
            ),
        )

    raise RuntimeError(
        "Unsupported document recovery "
        "lock backend."
    )


@contextmanager
def document_recovery_lock(
    *,
    db_path: str | None = None,
    environ: Mapping[str, str] | None = None,
    settings_loader: Callable = (
        load_database_settings
    ),
    connection_factory: Callable = (
        get_runtime_connection
    ),
    file_lock_factory: Callable = FileLock,
) -> Iterator[DocumentRecoveryLockLease]:
    lease = (
        try_acquire_document_recovery_lock(
            db_path=db_path,
            environ=environ,
            settings_loader=settings_loader,
            connection_factory=(
                connection_factory
            ),
            file_lock_factory=(
                file_lock_factory
            ),
        )
    )

    try:
        yield lease
    finally:
        lease.release()
