"""add_query_to_messages

Revision ID: 765e0c1bd195
Revises: 0002
Create Date: 2026-06-13

Changes:
  - messages: add query column (user's original question)
"""
from alembic import op
import sqlalchemy as sa

revision = "765e0c1bd195"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("query", sa.String(4000), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("messages", "query", schema="public")