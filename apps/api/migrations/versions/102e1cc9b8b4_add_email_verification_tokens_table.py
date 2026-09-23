"""add email_verification_tokens table

Revision ID: 102e1cc9b8b4
Revises: f8a3c5e7d9b1
Create Date: 2026-08-02

仮登録(アカウント作成 - 仮登録)フローのためのテーブル。
Userレコード作成前のメールアドレス確認に使用するため、
user_idではなくemailに紐付ける。

public-schema-only table. Parameterized via -x schema=<n> per ADR
001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since that table does not exist there.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "102e1cc9b8b4"
down_revision = "f8a3c5e7d9b1"
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

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_ip", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_token_hash"),
        schema="public",
    )
    op.create_index(
        "ix_email_verification_tokens_email",
        "email_verification_tokens",
        ["email"],
        schema="public",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return

    op.drop_index(
        "ix_email_verification_tokens_email",
        table_name="email_verification_tokens",
        schema="public",
    )
    op.drop_table("email_verification_tokens", schema="public")
