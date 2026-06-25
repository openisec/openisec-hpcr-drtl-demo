import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text
from alembic import context

from app.models.base import Base
from app.models.public_models import Organization, User, AuthToken, LoginSession  # noqa
from app.models.org_models import (  # noqa
    DecisionType, Agent, AgentPolicy, Preapproval,
    Session, Message, Approval, SafetyEvent, AuditLog,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_schema() -> str:
    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    # asyncpg -> psycopg2 (Alembicは同期接続が必要)
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("asyncpg://", "postgresql+psycopg2://")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=get_schema(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    schema = get_schema()
    connectable = create_engine(get_db_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=schema,
        )

        with context.begin_transaction():
            context.run_migrations()

        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()