"""add active_org_id to login_sessions

Revision ID: d3e4f5a6b7c8
Revises: c9d8e7f6a5b4
Create Date: 2026-07-12

Adds public.login_sessions.active_org_id (nullable UUID, FK to
organizations). Tracks which organization a session is currently
"switched into" for the /auth/switch-org flow, independent of the
user's home organization (users.organization_id). NULL means the
session has not switched away from the home org yet; callers should
fall back to users.organization_id in that case.

public-schema-only table. Parameterized via -x schema=<n> per ADR
001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since that table does not exist there.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "c9d8e7f6a5b4"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<n> passed on CLI. Defaults to public."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    if schema != "public":
        return

    op.add_column(
        "login_sessions",
        sa.Column(
            "active_org_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema="public",
    )
    op.create_foreign_key(
        "fk_login_sessions_active_org_id",
        source_table="login_sessions",
        referent_table="organizations",
        local_cols=["active_org_id"],
        remote_cols=["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return
    op.drop_constraint(
        "fk_login_sessions_active_org_id",
        "login_sessions",
        schema="public",
        type_="foreignkey",
    )
    op.drop_column("login_sessions", "active_org_id", schema="public")
