"""add tenant-only message fields (query, target_date, reason)

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-07-10

This migration exists because 765e0c1bd195, a1b2c3d4e5f6, and
b2c3d4e5f6a7 hardcoded schema="public" instead of being parameterized
per ADR 001. Those migrations already applied these columns to the
public schema historically. This migration adds the equivalent columns
to a tenant (org_*) schema when provisioning a new organization.

When run against the public schema (no -x schema= argument, or
schema=public), this migration is a no-op, since public already has
these columns from the earlier public-only migrations.

Run per org:
  alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    if schema == "public":
        # Public already has these columns from the earlier
        # (public-hardcoded) migrations. Nothing to do here.
        return

    op.add_column(
        "messages",
        sa.Column("query", sa.String(4000), nullable=True),
        schema=schema,
    )
    op.add_column(
        "messages",
        sa.Column("target_date", sa.Date(), nullable=True),
        schema=schema,
    )
    op.add_column(
        "messages",
        sa.Column("reason", sa.String(2000), nullable=True),
        schema=schema,
    )
    op.create_check_constraint(
        "chk_messages_reason_len",
        "messages",
        "reason IS NULL OR char_length(reason) <= 2000",
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()
    if schema == "public":
        return
    op.drop_constraint("chk_messages_reason_len", "messages", schema=schema)
    op.drop_column("messages", "reason", schema=schema)
    op.drop_column("messages", "target_date", schema=schema)
    op.drop_column("messages", "query", schema=schema)
