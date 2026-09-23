"""add addendum fields to messages (tenant-schema parameterized)

Revision ID: f8a3c5e7d9b1
Revises: e2f4a6c8b0d2
Create Date: 2026-07-26

G. 承認ワークフロー: closed/archived後の追記専用フィールド。
messages はテナント側テーブルのため、f1e2d3c4b5a6 と同じ方式で
schema引数をそのまま使う(public実行時はテンプレートのpublic.messages、
-x schema=org_xxx 実行時はそのテナントスキーマに対して適用される)。

Run against public (default):
  alembic upgrade head

Run per existing org:
  alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a3c5e7d9b1"
down_revision = "e2f4a6c8b0d2"
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
        sa.Column("addendum", sa.String(length=2000), nullable=True),
        schema=schema,
    )
    op.add_column(
        "messages",
        sa.Column("addendum_updated_at", sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.create_check_constraint(
        "chk_messages_addendum_len",
        "messages",
        "addendum IS NULL OR char_length(addendum) <= 2000",
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()
    op.drop_constraint("chk_messages_addendum_len", "messages", schema=schema)
    op.drop_column("messages", "addendum_updated_at", schema=schema)
    op.drop_column("messages", "addendum", schema=schema)
