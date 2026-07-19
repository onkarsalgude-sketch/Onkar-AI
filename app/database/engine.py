"""SQLAlchemy engine construction without schema initialization."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL
from sqlalchemy.pool import NullPool

from app.config.database import DatabaseSettings


def build_database_engine(
    settings: DatabaseSettings,
) -> Engine:
    """Build an engine without connecting to the database."""
    if settings.is_sqlite:
        sqlite_path = settings.sqlite_path.expanduser()
        sqlite_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        engine = create_engine(
            URL.create(
                "sqlite",
                database=str(sqlite_path),
            ),
            connect_args={
                "check_same_thread": False,
                "timeout": settings.connect_timeout_seconds,
            },
            poolclass=NullPool,
        )

        @event.listens_for(engine, "connect")
        def configure_sqlite_connection(
            dbapi_connection,
            _connection_record,
        ):
            cursor = dbapi_connection.cursor()

            try:
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute(
                    "PRAGMA busy_timeout = "
                    f"{settings.connect_timeout_seconds * 1000}"
                )
            finally:
                cursor.close()

        return engine

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=0,
        connect_args={
            "connect_timeout": (
                settings.connect_timeout_seconds
            ),
            "application_name": "onkar-ai",
        },
    )
