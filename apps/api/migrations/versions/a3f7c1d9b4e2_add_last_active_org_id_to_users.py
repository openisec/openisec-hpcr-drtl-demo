"""add last_active_org_id to users

Revision ID: a3f7c1d9b4e2
Revises: d4e7f9a1c3b5
Create Date: 2026-08-11

ログインし直した際、ホーム組織ではなく直近でスイッチしていた組織を
初期アクティブ組織として引き継げるようにするためのカラム。
switch-org成功時に更新し、ログイン時のLoginSession.active_org_id初期値
として利用する。

public-schema-only table. Parameterized via -x schema=<n> per ADR
001: no-ops when run against a tenant (org_*) schema during
provision_org_schema(), since users table does not exist there.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a3f7c1d9b4e2"
down_revision = "d4e7f9a1c3b5"
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

    op.add_column(
        "users",
        sa.Column(
            "last_active_org_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema="public",
    )
    op.create_foreign_key(
        "fk_users_last_active_org_id_organizations",
        "users",
        "organizations",
        ["last_active_org_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return

    op.drop_constraint(
        "fk_users_last_active_org_id_organizations",
        "users",
        schema="public",
        type_="foreignkey",
    )
    op.drop_column("users", "last_active_org_id", schema="public")
