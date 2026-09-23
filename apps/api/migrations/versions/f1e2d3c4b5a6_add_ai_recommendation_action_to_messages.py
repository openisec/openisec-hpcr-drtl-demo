"""add ai_recommendation_action to messages (tenant-schema parameterized)

Revision ID: f1e2d3c4b5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-07-25

Adds a new column recording the user's judgement on the AI's
recommendation (adopted / modified / rejected) at Decision/Log time.
This is a brand-new field for both `public` and tenant (org_*) schemas
-- unlike d1e2f3a4b5c6, there is no historical public-only migration
that already added it, so (following the same pattern as a7b8c9d0e1f2)
this migration adds the column unconditionally regardless of the
target schema.

Run against public (default):
  alembic upgrade head

Run per existing org:
  alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "f1e2d3c4b5a6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI. Defaults to public."""
    from alembic import context  # local import avoids circular
    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    op.add_column(
        "messages",
        sa.Column("ai_recommendation_action", sa.String(length=20), nullable=True),
        schema=schema,
    )
    op.create_check_constraint(
        "chk_messages_ai_recommendation_action_values",
        "messages",
        "ai_recommendation_action IS NULL OR ai_recommendation_action IN ('adopted', 'modified', 'rejected')",
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()
    op.drop_constraint(
        "chk_messages_ai_recommendation_action_values", "messages", schema=schema
    )
    op.drop_column("messages", "ai_recommendation_action", schema=schema)
