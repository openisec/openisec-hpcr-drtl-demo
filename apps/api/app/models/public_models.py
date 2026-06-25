"""
Public schema models — shared across all tenants.

Tables:
  - organizations
  - users
  - auth_tokens
  - login_sessions
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    """
    Tenant root. Each org gets its own PostgreSQL schema: org_{id}.
    OWASP LLM06: Agent permissions are scoped per organization.
    """

    __tablename__ = "organizations"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False, unique=True)
    # Schema name for this org's data: org_{id without hyphens}
    pg_schema: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # OWASP LLM10: org-level token budget
    monthly_token_budget: Mapped[int] = mapped_column(
        Integer, default=1_000_000, nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base, TimestampMixin):
    """
    Platform user. Password stored as Argon2id hash (never plaintext).
    OWASP A02:2021 — Cryptographic Failures addressed via Argon2id.
    """

    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    # Argon2id hash — never store plaintext passwords
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="member"
    )  # owner | admin | approver | member
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        {"schema": "public"},
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    auth_tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user")
    login_sessions: Mapped[list["LoginSession"]] = relationship(back_populates="user")


class AuthToken(Base):
    """
    Short-lived tokens for email verification and password reset.
    OWASP A07: Authentication — tokens expire and are single-use.
    """

    __tablename__ = "auth_tokens"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )  # SHA-256 of the raw token
    purpose: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # email_verify | password_reset
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="auth_tokens")


class LoginSession(Base):
    """
    Server-side session record. Cookie stores only the session_id.
    OWASP A07: HTTPOnly + Secure + SameSite=Lax enforced at API layer.
    """

    __tablename__ = "login_sessions"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="login_sessions")
