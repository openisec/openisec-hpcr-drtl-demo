import re
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings

settings = get_settings()

# Engine is created once at module load time and reused across requests.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Allowed schema names: "public" or "org_" + 32-36 hex/underscore chars
_SCHEMA_NAME_PATTERN = re.compile(r"^(public|org_[0-9a-f_]{32,36})$")
_FORBIDDEN_SCHEMAS = {"information_schema", "pg_catalog"}


def _validate_schema_name(schema: str) -> None:
    if schema in _FORBIDDEN_SCHEMAS or schema.startswith("pg_"):
        raise ValueError(f"Forbidden schema name: {schema!r}")
    if not _SCHEMA_NAME_PATTERN.match(schema):
        raise ValueError(f"Invalid schema name: {schema!r}")


def schema_exists(db: Session, schema: str) -> bool:
    """
    Lightweight check for whether a tenant schema physically exists.
    Used by get_org_db to detect the "organizations row committed but
    schema never provisioned" failure mode and trigger self-healing.
    """
    _validate_schema_name(schema)
    row = db.execute(
        text("SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = :schema"),
        {"schema": schema},
    ).first()
    return row is not None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_schema(db: Session, schema: str) -> None:
    """
    Session-level schema switch, kept for backward compatibility.
    Prefer tenant_schema() for new code (transaction-scoped).
    """
    _validate_schema_name(schema)
    db.execute(text(f"SET search_path TO {schema}, public"))
    db.flush()


@contextmanager
def tenant_schema(db: Session, schema: str):
    """
    Transaction-scoped search_path switch. Only valid within the
    'with tenant_schema(db, org.pg_schema):' block; automatically
    reverts when the block exits, since SET LOCAL resets at
    transaction end.

    If the session already has an active transaction (SQLAlchemy 2.0
    autobegin - e.g. a prior db.query() in get_current_user already
    started one), reuse it instead of calling db.begin() again, which
    would raise "A transaction is already begun on this Session."
    """
    _validate_schema_name(schema)
    if db.in_transaction():
        db.execute(text(f"SET LOCAL search_path TO {schema}, public"))
        yield db
    else:
        with db.begin():
            db.execute(text(f"SET LOCAL search_path TO {schema}, public"))
            yield db
