"""rename full_name to family_name, add given_name

Revision ID: a7c9e1f3d5b2
Revises: f1e2d3c4b5a6
Create Date: 2026-07-25

users is a public-schema-only table. Parameterized via -x schema=<n>
per ADR 001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since that table does not exist there.
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c9e1f3d5b2"
down_revision = "f1e2d3c4b5a6"
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

    # 1. full_name -> family_name へリネーム(データそのまま引き継ぎ)
    op.alter_column(
        "users",
        "full_name",
        new_column_name="family_name",
        schema="public",
    )

    # 2. given_name を nullable で追加
    op.add_column(
        "users",
        sa.Column("given_name", sa.String(length=100), nullable=True),
        schema="public",
    )

    # 3. 既存行に仮値(空文字)を投入
    op.execute("UPDATE public.users SET given_name = '' WHERE given_name IS NULL")

    # 4. NOT NULL制約を確定 + server_default設定
    op.alter_column(
        "users",
        "given_name",
        nullable=False,
        server_default="",
        schema="public",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return
    op.alter_column(
        "users",
        "given_name",
        nullable=True,
        server_default=None,
        schema="public",
    )
    op.drop_column("users", "given_name", schema="public")
    op.alter_column(
        "users",
        "family_name",
        new_column_name="full_name",
        schema="public",
    )
