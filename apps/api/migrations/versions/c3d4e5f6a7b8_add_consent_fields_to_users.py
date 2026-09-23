"""add consent fields to users

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-08

Changes:
    - users: add terms_version, privacy_policy_version (agreed document versions)
    - users: add agreed_terms_at, agreed_privacy_at (consent timestamps)
    - users: add marketing_opt_in, marketing_opt_in_at, marketing_opt_out_at
    - users: add ip_address, user_agent (recorded at registration)
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('terms_version', sa.String(20), nullable=True), schema='public')
    op.add_column('users', sa.Column('privacy_policy_version', sa.String(20), nullable=True), schema='public')
    op.add_column('users', sa.Column('agreed_terms_at', sa.DateTime(timezone=True), nullable=True), schema='public')
    op.add_column('users', sa.Column('agreed_privacy_at', sa.DateTime(timezone=True), nullable=True), schema='public')
    op.add_column('users', sa.Column('marketing_opt_in', sa.Boolean(), nullable=False, server_default=sa.false()), schema='public')
    op.add_column('users', sa.Column('marketing_opt_in_at', sa.DateTime(timezone=True), nullable=True), schema='public')
    op.add_column('users', sa.Column('marketing_opt_out_at', sa.DateTime(timezone=True), nullable=True), schema='public')
    op.add_column('users', sa.Column('ip_address', sa.String(45), nullable=True), schema='public')
    op.add_column('users', sa.Column('user_agent', sa.String(500), nullable=True), schema='public')


def downgrade() -> None:
    op.drop_column('users', 'user_agent', schema='public')
    op.drop_column('users', 'ip_address', schema='public')
    op.drop_column('users', 'marketing_opt_out_at', schema='public')
    op.drop_column('users', 'marketing_opt_in_at', schema='public')
    op.drop_column('users', 'marketing_opt_in', schema='public')
    op.drop_column('users', 'agreed_privacy_at', schema='public')
    op.drop_column('users', 'agreed_terms_at', schema='public')
    op.drop_column('users', 'privacy_policy_version', schema='public')
    op.drop_column('users', 'terms_version', schema='public')