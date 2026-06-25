"""add reason to messages

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22

Changes:
    - messages: add reason column (human's reason for adopting/modifying/rejecting AI recommendation)
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('reason', sa.String(2000), nullable=True),
        schema='public'
    )
    op.create_check_constraint(
        'chk_messages_reason_len',
        'messages',
        'reason IS NULL OR char_length(reason) <= 2000',
        schema='public'
    )


def downgrade() -> None:
    op.drop_constraint('chk_messages_reason_len', 'messages', schema='public')
    op.drop_column('messages', 'reason', schema='public')