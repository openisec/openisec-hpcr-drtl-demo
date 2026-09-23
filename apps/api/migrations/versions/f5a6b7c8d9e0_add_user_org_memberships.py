"""add user_org_memberships table

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-11

Introduces a lightweight multi-membership table so a single user
(currently: the Openisec platform admin account only) can belong to
more than one organization, while everyone else keeps the existing
single-org shape. users.organization_id / users.role remain the
"home org" and are unchanged by this migration.

Backfills one membership row per existing user, mirroring their
current organization_id/role, so existing behavior is preserved.

public-schema-only table. Parameterized via -x schema=<n> per ADR
001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since this table only ever lives in public.
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
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

    op.create_table(
        "user_org_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id", "organization_id", name="uq_user_org_membership"
        ),
        schema="public",
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, organization_id, role FROM public.users")
    ).fetchall()

    now = datetime.now(timezone.utc)
    membership_table = sa.table(
        "user_org_memberships",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("organization_id", postgresql.UUID(as_uuid=True)),
        sa.column("role", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        schema="public",
    )

    if rows:
        conn.execute(
            membership_table.insert(),
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": row.id,
                    "organization_id": row.organization_id,
                    "role": row.role,
                    "created_at": now,
                    "updated_at": now,
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return
    op.drop_table("user_org_memberships", schema="public")
