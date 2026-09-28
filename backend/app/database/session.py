"""SQLAlchemy engine and session factory."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def resolve_database_url(url: str) -> str:
    """Point relative SQLite files at the project root so cwd does not matter."""

    if not url.startswith("sqlite") or ":memory:" in url:
        return url
    _, _, rest = url.partition(":///")
    if rest.startswith("./") or (rest and not Path(rest).is_absolute()):
        db_path = (_PROJECT_ROOT / rest.lstrip("./")).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+pysqlite:///{db_path.as_posix()}"
    return url


def _create_engine() -> Engine:
    settings = get_settings()
    database_url = resolve_database_url(settings.database_url)
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool
    engine_kwargs["connect_args"] = connect_args
    return create_engine(database_url, **engine_kwargs)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> None:
    """Raise if PostgreSQL (or the configured engine) is unreachable."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database_health_check_failed")
        raise


def _migrate_columns() -> None:
    """Ensure columns added in newer models exist in the database."""
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if inspector.has_table("review_runs"):
            existing = {c["name"] for c in inspector.get_columns("review_runs")}
            with engine.begin() as conn:
                if "resolved_config" not in existing:
                    col_type = "JSONB" if engine.dialect.name == "postgresql" else "JSON"
                    conn.execute(text(f"ALTER TABLE review_runs ADD COLUMN resolved_config {col_type}"))
                if "config_sha" not in existing:
                    conn.execute(text("ALTER TABLE review_runs ADD COLUMN config_sha VARCHAR(64)"))
    except Exception as exc:
        logger.warning("column_migration_skipped", error=str(exc))


def init_database() -> None:
    """Create tables if they do not exist. Migrations will replace this later."""

    from app.database import models  # noqa: F401  ensure models are registered

    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    log_event = get_logger("app.database")
    log_event.info("database_schema_ready")

