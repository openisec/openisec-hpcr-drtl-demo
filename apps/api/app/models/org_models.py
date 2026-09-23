"""
Org-scoped schema models - one schema per organization: org_{uuid}.

These models intentionally omit an explicit schema= in __table_args__.
Without an explicit schema, SQLAlchemy emits unqualified table names,
which means the active PostgreSQL search_path determines which schema
is actually queried. This is what allows app.core.database.tenant_schema()
to route requests to org_{uuid} via SET LOCAL search_path.

See: docs/adr/001-multitenant-schema.md
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DecisionType(Base, TimestampMixin):
    __tablename__ = "decision_types"
    __table_args__ = (
        UniqueConstraint("org_id", "code", name="uq_decision_types_org_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, default="gemini-2.0-flash")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    max_tokens_per_call: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    policies: Mapped[list["AgentPolicy"]] = relationship(
        "AgentPolicy",
        back_populates="agent",
        foreign_keys="[AgentPolicy.agent_id]",
    )


class AgentPolicy(Base, TimestampMixin):
    __tablename__ = "agent_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id"),
        nullable=False,
    )
    policy_type: Mapped[str] = mapped_column(String(20), nullable=False)
    action_pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="policies",
        foreign_keys=[agent_id],
    )


class Preapproval(Base, TimestampMixin):
    __tablename__ = "preapprovals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applicable_agent_types: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    decision_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="Human")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    # 下書き状態でのクエリ入力途中内容を保持するためのフィールド(D. ログ閲覧改善)
    draft_query: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        foreign_keys="[Message.session_id]",
    )
    approvals: Mapped[list["Approval"]] = relationship(
        "Approval",
        back_populates="session",
        foreign_keys="[Approval.session_id]",
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("char_length(history) <= 2000", name="chk_messages_history_len"),
        CheckConstraint("char_length(recommendation) <= 1000", name="chk_messages_recommendation_len"),
        CheckConstraint("char_length(decision) <= 1000", name="chk_messages_decision_len"),
        CheckConstraint("reason IS NULL OR char_length(reason) <= 2000", name="chk_messages_reason_len"),
        CheckConstraint("log IS NULL OR char_length(log) <= 500", name="chk_messages_log_len"),
        CheckConstraint(
            "ai_recommendation_action IS NULL OR ai_recommendation_action IN ('adopted', 'modified', 'rejected')",
            name="chk_messages_ai_recommendation_action_values",
        ),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="chk_messages_risk_score_range"),
        CheckConstraint("response_confidence_score >= 0 AND response_confidence_score <= 100", name="chk_messages_confidence_range"),
        CheckConstraint("addendum IS NULL OR char_length(addendum) <= 2000", name="chk_messages_addendum_len"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
    )
    query: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    history: Mapped[str] = mapped_column(String(2000), nullable=False)
    pro: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    con: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recommendation: Mapped[str] = mapped_column(String(1000), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decision_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # AIの推奨に対するユーザーの判定(採用/修正/見送り)。UI表示は日本語だが、
    # 将来の多言語UI対応を見据え、DBには英語コードで保存する。
    # decision/reason と同じく「進行中(未確定)」と「確定」で共用するカラム。
    ai_recommendation_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(sa.Date(), nullable=True)
    log: Mapped[str | None] = mapped_column(String(500), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="Human")
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    relevant_preapproval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    decision_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    risk_category: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    response_confidence_score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    response_confidence_level: Mapped[str] = mapped_column(String(30), nullable=False, default="low")
    response_confidence_limiting_factors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    input_guardrail_result: Mapped[str | None] = mapped_column(String(10), nullable=True)
    input_guardrail_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_guardrail_result: Mapped[str | None] = mapped_column(String(10), nullable=True)
    output_guardrail_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    raw_ai_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # G. 完了(closed)/終了(archived)後の追記専用フィールド。
    # decision/reason等の確定フィールドは編集不可のため、追記のみここに残す。
    addendum: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    addendum_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="messages",
        foreign_keys=[session_id],
    )


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="approvals",
        foreign_keys=[session_id],
    )


class SafetyEvent(Base):
    __tablename__ = "safety_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # 「AさんがBさんのロールを変更した」等、操作対象のユーザー。
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
