"""add CTQP fields (curiosity, prior_thinking) to sessions (tenant-schema parameterized)

Revision ID: b4c5d6e7f8a9
Revises: a3f7c1d9b4e2
Create Date: 2026-10-21

CTQP integration: a decision session now records, per session,
  - curiosity      (C: what prompted the user to raise this question)
  - prior_thinking (T: what the user already thinks before asking the AI)
alongside the existing Query (Q, stored on messages.query).

Both columns are NULLABLE on purpose: sessions created before this change
have no C/T values and must keep rendering (backward compatibility).
New analyses require both values at the API layer (see MessageRequest).
C/T are stored here and passed to the AI analysis together with Q (as structured fields).

Per ADR 001, `sessions` lives in each org's tenant schema (org_<uuid>),
with `public` also carrying a historical copy. This migration is
parameterized via `-x schema=<name>` and must be run once against
`public` (default, no -x needed) AND once per existing org schema.
New orgs provisioned after this migration pick it up automatically via
provision_org_schema().

Run against public (default):
  python -m alembic upgrade head

Run per existing org:
  python -m alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
down_revision = "a3f7c1d9b4e2"
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
        sa.Column("curiosity", sa.String(length=1000), nullable=True),
        schema=schema,
    )
    op.add_column(
        "sessions",
        sa.Column("prior_thinking", sa.String(length=1000), nullable=True),
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()
    op.drop_column("sessions", "prior_thinking", schema=schema)
    op.drop_column("sessions", "curiosity", schema=schema)
