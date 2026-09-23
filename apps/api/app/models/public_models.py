"""
Public schema models — shared across all tenants.

Tables:
  - organizations
  - users
  - auth_tokens
  - login_sessions
  - email_verification_tokens
  - auth_audit_logs
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # E: この値以上のrisk_scoreが算出されたLogに対し、G(事前承認ワークフロー)の
    # 承認者通知・承認フローがトリガーされる。組織admin(自組織のみ)/
    # Platform admin(全組織)が「管理設定」>「リスクスコア閾値設定」で変更可能。
    risk_score_threshold: Mapped[int] = mapped_column(
        Integer, default=70, nullable=False
    )
    # 2026-08: この組織が「個人」組織(1人専用)かどうか。register()時に
    # 組織名が個人組織命名規則(「個人」/"personal")に一致した場合に true。
    # メンバー管理での組織変更時、他人の個人組織へ誤ってマッピングされる
    # ことを防ぐガードに使用する(User.personal_org_id と併用)。
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # organizations <-> users 間には organization_id (所属先) と
    # personal_org_id (本人の個人組織) の2本のFKが存在するため、
    # このリレーションシップがどちらを辿るか明示する必要がある
    # (指定しないと AmbiguousForeignKeysError になる)。
    users: Mapped[list["User"]] = relationship(
        back_populates="organization",
        foreign_keys="[User.organization_id]",
    )


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
    # 2026-07: full_name を family_name にリネームし、given_name を新設。
    # 既存データは全て family_name(旧full_name)に引き継がれ、
    # given_name は移行完了まで空文字("")が入る。
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    given_name: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=""
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="member"
    )  # owner | admin | approver | member
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 直近でアクティブだった組織。新規ログインセッション作成時の初期
    # active_org_idにこれを使うことで、ログインし直してもホーム組織へ
    # 戻らず、前回スイッチした組織が引き継がれる。switch-org成功時に更新。
    last_active_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # --- Consent tracking (added 2026-07) ---
    terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    privacy_policy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agreed_terms_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agreed_privacy_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    marketing_opt_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    marketing_opt_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 2026-08: このユーザー自身の「個人」組織のID(存在する場合)。
    # register()で個人組織を作成した際に恒久的に設定され、以後の組織変更
    # (個人→組織メンバー→個人 等)を経ても書き換わらない。メンバー管理で
    # 他人の個人組織へ誤ってマッピングされることを防ぐガードに使用する。
    personal_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        {"schema": "public"},
    )

    organization: Mapped["Organization"] = relationship(
        back_populates="users",
        foreign_keys=[organization_id],
    )
    auth_tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user")
    login_sessions: Mapped[list["LoginSession"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        """
        表示用の氏名。family_name + 半角スペース + given_name。
        given_name が未移行(空文字)の場合は family_name のみを返す。
        既存コードとの互換のため full_name という名前の read-only
        プロパティとして提供する(DBカラムではない)。
        """
        given = self.given_name.strip() if self.given_name else ""
        if given:
            return f"{self.family_name} {given}"
        return self.family_name


class UserOrgMembership(Base, TimestampMixin):
    """
    Lightweight multi-org membership. Almost all users have exactly
    one row here, mirroring users.organization_id/role (their "home
    org"). Only the Openisec platform admin account currently has
    more than one row, granting admin-role access to manage members
    across multiple organizations without a "superadmin" concept or
    direct data access to tenant schemas.
    """

    __tablename__ = "user_org_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_org_membership"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")


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
    active_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="login_sessions")


class EmailVerificationToken(Base):
    """
    Pre-registration email verification tokens.
    Issued before a User record exists — keyed by email, not user_id.
    OWASP A07: token stored as SHA-256 hash, single-use, short expiry.
    """

    __tablename__ = "email_verification_tokens"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AuthAuditLog(Base):
    """
    認証・認可レベルの監査ログ(public schema)。

    ログイン成功/失敗、ログアウト、パスワード変更、メールアドレス確認、
    組織切り替え、メンバー管理(追加/削除/ロール変更)など、特定の組織の
    テナントスキーマに一意に紐づかない、または組織所属確定前に発生しうる
    イベントを記録する。

    組織スコープの操作(セッションの完了/終了、承認/却下、リスクスコア
    閾値変更等)は org_<uuid>.audit_logs (org_models.AuditLog) 側に記録する。
    """

    __tablename__ = "auth_audit_logs"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # ログイン失敗時など、actor_id が特定できない場合がある。
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    # 組織切り替え・メンバー管理など、対象組織が明確なイベントのみ設定。
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # 「AさんがBさんのロールを変更した」等、操作対象のユーザー。
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
