"""add auth_audit_logs (public) and extend audit_logs (tenant-schema parameterized)

Revision ID: c2e5a9f1b3d7
Revises: b6d4f8a2c1e7
Create Date: 2026-08-08

監査ログ基盤の第一段階。

1. public.auth_audit_logs (新規、public-schema-only):
   ログイン成功/失敗・ログアウト・パスワード変更・メール確認・組織切り替え・
   メンバー管理など、特定の組織のテナントスキーマに一意に紐づかない、または
   組織所属確定前に発生しうるイベントを記録する。102e1cc9b8b4と同じ方式で
   ADR 001ガード(schema != "public"ならno-op)を適用する。

2. audit_logs (既存、テナント側): actor_email / target_user_id 列を追加。
   f8a3c5e7d9b1と同じ方式でschema引数をそのまま使う(ガードなし)。

Run against public (default):
  alembic upgrade head

Run per existing org (audit_logsへの列追加を確実に当てる場合):
  alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c2e5a9f1b3d7"
down_revision = "b6d4f8a2c1e7"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI. Defaults to public."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def _create_auth_audit_logs_table(schema: str) -> None:
    if schema != "public":
        return
    op.create_table(
        "auth_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema="public",
    )
    op.create_index(
        "ix_auth_audit_logs_actor_id",
        "auth_audit_logs",
        ["actor_id"],
        schema="public",
    )
    op.create_index(
        "ix_auth_audit_logs_occurred_at",
        "auth_audit_logs",
        ["occurred_at"],
        schema="public",
    )


def _drop_auth_audit_logs_table(schema: str) -> None:
    if schema != "public":
        return
    op.drop_index("ix_auth_audit_logs_occurred_at", table_name="auth_audit_logs", schema="public")
    op.drop_index("ix_auth_audit_logs_actor_id", table_name="auth_audit_logs", schema="public")
    op.drop_table("auth_audit_logs", schema="public")


def upgrade() -> None:
    schema = _schema()

    _create_auth_audit_logs_table(schema)

    # audit_logs (テナント側) への列追加は public/org_* いずれの実行でも行う。
    op.add_column(
        "audit_logs",
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        schema=schema,
    )
    op.add_column(
        "audit_logs",
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()

    op.drop_column("audit_logs", "target_user_id", schema=schema)
    op.drop_column("audit_logs", "actor_email", schema=schema)

    _drop_auth_audit_logs_table(schema)
