"""add risk_score_threshold to organizations

Revision ID: e2f4a6c8b0d2
Revises: b3d8f2a6c9e4
Create Date: 2026-07-26

organizations is a public-schema-only table. Parameterized via
-x schema=<n> per ADR 001: no-ops when run against a tenant (org_*)
schema during provision_org_schema(), since that table does not
exist there.
"""
from alembic import op
import sqlalchemy as sa

revision = "e2f4a6c8b0d2"
down_revision = "b3d8f2a6c9e4"
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
        "organizations",
        sa.Column(
            "risk_score_threshold",
            sa.Integer(),
            nullable=False,
            server_default="70",
        ),
        schema="public",
    )


def downgrade() -> None:
    schema = _schema()
    if schema != "public":
        return

    op.drop_column("organizations", "risk_score_threshold", schema="public")
