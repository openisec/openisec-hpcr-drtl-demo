"""add must_change_password to users

Revision ID: e4f5a6b7c8d9
Revises: d1e2f3a4b5c6
Create Date: 2026-07-11

users is a public-schema-only (metadata) table. Parameterized via
-x schema=<n> per ADR 001 (see d1e2f3a4b5c6 / a7b8c9d0e1f2 for the
established pattern): no-ops when run against a tenant (org_*)
schema during provision_org_schema(), since that table does not
exist there.
"""
from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d1e2f3a4b5c6"
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
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="public",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return
    op.drop_column("users", "must_change_password", schema="public")
