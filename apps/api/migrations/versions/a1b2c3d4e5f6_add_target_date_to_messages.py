"""add target_date to messages

Revision ID: a1b2c3d4e5f6
Revises: 765e0c1bd195
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '765e0c1bd195'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('target_date', sa.Date(), nullable=True),
        schema='public'
    )


def downgrade() -> None:
    op.drop_column('messages', 'target_date', schema='public')