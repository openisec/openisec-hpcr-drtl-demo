"""shrink family_name to varchar(100)

Revision ID: b3d8f2a6c9e4
Revises: a7c9e1f3d5b2
Create Date: 2026-07-25

users is a public-schema-only table. Parameterized via -x schema=<n>
per ADR 001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since that table does not exist there.
"""
from alembic import op
import sqlalchemy as sa

revision = "b3d8f2a6c9e4"
down_revision = "a7c9e1f3d5b2"
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

    op.alter_column(
        "users",
        "family_name",
        type_=sa.String(length=100),
        existing_type=sa.String(length=200),
        schema="public",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return
    op.alter_column(
        "users",
        "family_name",
        type_=sa.String(length=200),
        existing_type=sa.String(length=100),
        schema="public",
    )
