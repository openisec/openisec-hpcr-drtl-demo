"""Initial migration: public schema

Revision ID: 0001
Revises:
Create Date: 2026-06-07

Creates:
  - public.organizations
  - public.users
  - public.auth_tokens
  - public.login_sessions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure public schema exists
    op.execute("CREATE SCHEMA IF NOT EXISTS public")

    # --- organizations -----------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False, unique=True),
        sa.Column("pg_schema", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="50"),
        sa.Column(
            "monthly_token_budget",
            sa.Integer(),
            nullable=False,
            server_default="1000000",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="public",
    )

    # --- users -------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_login_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        schema="public",
    )
    op.create_index(
        "ix_users_email", "users", ["email"], schema="public"
    )
    op.create_index(
        "ix_users_organization_id", "users", ["organization_id"], schema="public"
    )

    # --- auth_tokens -------------------------------------------------------
    op.create_table(
        "auth_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="public",
    )
    op.create_index(
        "ix_auth_tokens_token_hash", "auth_tokens", ["token_hash"], schema="public"
    )

    # --- login_sessions ----------------------------------------------------
    op.create_table(
        "login_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_token_hash", sa.String(128), nullable=False, unique=True
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        schema="public",
    )
    op.create_index(
        "ix_login_sessions_user_id",
        "login_sessions",
        ["user_id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("login_sessions", schema="public")
    op.drop_table("auth_tokens", schema="public")
    op.drop_table("users", schema="public")
    op.drop_table("organizations", schema="public")
