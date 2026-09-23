"""add draft_query to sessions (tenant-schema parameterized)

Revision ID: a7b8c9d0e1f2
Revises: d3e4f5a6b7c8
Create Date: 2026-07-22

Per ADR 001, `sessions` lives in each org's tenant schema (org_<uuid>),
with `public` also carrying a historical copy (see d1e2f3a4b5c6 for
background on why public ended up with tenant-table columns too).

This migration is parameterized via `-x schema=<name>` and must be run
once against `public` (default, no -x needed) AND once per existing
org schema. New orgs provisioned after this migration will pick it up
automatically via provision_org_schema().

Run against public (default):
  alembic upgrade head

Run per existing org:
  alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI. Defaults to public."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    op.add_column(
        "sessions",
        sa.Column("draft_query", sa.String(length=4000), nullable=True),
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()
    op.drop_column("sessions", "draft_query", schema=schema)
