from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import get_settings


def get_db() -> Generator[Session, None, None]:
    settings = get_settings()
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_schema(db: Session, schema: str) -> None:
    db.execute(text(f"SET search_path TO {schema}, public"))
    db.flush()