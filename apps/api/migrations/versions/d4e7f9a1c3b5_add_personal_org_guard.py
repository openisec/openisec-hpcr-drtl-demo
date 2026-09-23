"""add is_personal to organizations and personal_org_id to users

Revision ID: d4e7f9a1c3b5
Revises: c2e5a9f1b3d7
Create Date: 2026-08-09

organizations と users はいずれも public-schema-only テーブル。
ADR 001 ガード(schema != "public" ならno-op)を適用する。

背景: 「個人」組織はその人専用(1対1)であるべきだが、これまでは
名称("個人"/"personal")のみで判定しており、DB上に恒久的な紐付けが
存在しなかった。組織変更(個人→組織メンバー→個人 等)を経ても、
必ず本人の個人組織に戻れるよう、以下を追加する。

  - organizations.is_personal: このレコードが「個人」組織かどうか
  - users.personal_org_id: このユーザー自身の個人組織のID(存在する場合)

既存データの移行: 名称が個人組織命名規則に一致する組織を is_personal=true
とし、その組織に所属する唯一のメンバーの personal_org_id を設定する。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e7f9a1c3b5"
down_revision = "c2e5a9f1b3d7"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI. Defaults to public."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    if schema != "public":
        return

    op.add_column(
        "organizations",
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default="false"),
        schema="public",
    )
    op.add_column(
        "users",
        sa.Column("personal_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_users_personal_org_id_organizations",
        "users",
        "organizations",
        ["personal_org_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="SET NULL",
    )

    # 既存データ移行: 名称が個人組織命名規則(「個人」/"personal", 大小無視)
    # に一致する組織を is_personal=true とし、そのメンバー(1組織1人想定)の
    # personal_org_id を設定する。
    op.execute(
        """
        UPDATE public.organizations
        SET is_personal = true
        WHERE lower(name) IN ('個人', 'personal')
        """
    )
    op.execute(
        """
        UPDATE public.users u
        SET personal_org_id = m.organization_id
        FROM public.user_org_memberships m
        JOIN public.organizations o ON o.id = m.organization_id
        WHERE m.user_id = u.id AND o.is_personal = true
        """
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return

    op.drop_constraint(
        "fk_users_personal_org_id_organizations", "users", schema="public", type_="foreignkey"
    )
    op.drop_column("users", "personal_org_id", schema="public")
    op.drop_column("organizations", "is_personal", schema="public")
