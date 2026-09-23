"""add is_platform_admin to users

Revision ID: c9d8e7f6a5b4
Revises: f5a6b7c8d9e0
Create Date: 2026-07-12

Adds public.users.is_platform_admin (bool, default false). This flag
grants cross-organization membership-management privileges to the
Openisec platform admin account only. Backfills True for
admin@openisec.com.

public-schema-only table. Parameterized via -x schema=<n> per ADR
001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since that table does not exist there.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c9d8e7f6a5b4"
down_revision = "f5a6b7c8d9e0"
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
        "users",
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="public",
    )
    op.execute(
        """
        UPDATE public.users
        SET is_platform_admin = true
        WHERE email = 'admin@openisec.com'
        """
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return
    op.drop_column("users", "is_platform_admin", schema="public")
