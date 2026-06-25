"""
Org-scoped schema models  Eone schema per organization: org_{uuid}.
"""
# TODO: [PHASE-2] Multi-tenant schema implementation
# Currently ORG_SCHEMA = "org_schema" is a placeholder.
# In Phase 2, each organization should have its own PostgreSQL schema: org_{uuid}.
# Implementation steps:
#   1. On org creation, run: CREATE SCHEMA org_{uuid}
#   2. Run migration 0002 against that schema
#   3. deps.py get_org_db() dynamically sets search_path to org_{uuid}
#   4. ORG_SCHEMA should be replaced with dynamic schema name at runtime
# See: docs/adr/001-multitenant-schema.md
ORG_SCHEMA = "public"  # TODO: [PHASE-2] Replace with dynamic org_{uuid} schema

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

ORG_SCHEMA = "org_schema"


# ---------------------------------------------------------------------------
# Decision Types
# ---------------------------------------------------------------------------
class DecisionType(Base, TimestampMixin):
    __tablename__ = "decision_types"
    __table_args__ = (
        UniqueConstraint("org_id", "code", name="uq_decision_types_org_code"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ---------------------------------------------------------------------------
# AI Agent Registry
# ---------------------------------------------------------------------------
class Agent(Base, TimestampMixin):
    __tablename__ = "agents"
    __table_args__ = {"schema": "public"}

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


# ---------------------------------------------------------------------------
# Agent Policies
# ---------------------------------------------------------------------------
class AgentPolicy(Base, TimestampMixin):
    __tablename__ = "agent_policies"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.agents.id"),
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


# ---------------------------------------------------------------------------
# Preapproval Center
# ---------------------------------------------------------------------------
class Preapproval(Base, TimestampMixin):
    __tablename__ = "preapprovals"
    __table_args__ = {"schema": "public"}

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


# ---------------------------------------------------------------------------
# Decision Sessions
# ---------------------------------------------------------------------------
class Session(Base, TimestampMixin):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    decision_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="Human")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

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


# ---------------------------------------------------------------------------
# HPCRDTL Message  Ecore table
# ---------------------------------------------------------------------------
class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("char_length(history) <= 2000", name="chk_messages_history_len"),
        CheckConstraint("char_length(recommendation) <= 1000", name="chk_messages_recommendation_len"),
        CheckConstraint("char_length(decision) <= 1000", name="chk_messages_decision_len"),
        CheckConstraint("reason IS NULL OR char_length(reason) <= 2000", name="chk_messages_reason_len"),
        CheckConstraint("log IS NULL OR char_length(log) <= 500", name="chk_messages_log_len"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="chk_messages_risk_score_range"),
        CheckConstraint("response_confidence_score >= 0 AND response_confidence_score <= 100", name="chk_messages_confidence_range"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.sessions.id"),
        nullable=False,
    )
    # User's original question
    query: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # H
    history: Mapped[str] = mapped_column(String(2000), nullable=False)
    # P
    pro: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # C
    con: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # R
    recommendation: Mapped[str] = mapped_column(String(1000), nullable=False)
    # D
    decision: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decision_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # R (Reason)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # T
    target_date: Mapped[datetime | None] = mapped_column(sa.Date(), nullable=True)
    # L
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

    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="messages",
        foreign_keys=[session_id],
    )


# ---------------------------------------------------------------------------
# Approval Inbox
# ---------------------------------------------------------------------------
class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.sessions.id"),
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


# ---------------------------------------------------------------------------
# Safety Events
# ---------------------------------------------------------------------------
class SafetyEvent(Base):
    __tablename__ = "safety_events"
    __table_args__ = {"schema": "public"}

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


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
