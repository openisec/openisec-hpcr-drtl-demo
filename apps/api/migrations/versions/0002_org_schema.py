"""Org schema template: HPCRDTL core tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07

Run per org:
  alembic -x schema=org_<uuid_no_hyphens> upgrade head

Creates (in the target org schema):
  - decision_types
  - agents
  - agent_policies
  - preapprovals
  - sessions
  - messages         ← HPCRDTL core with CHECK constraints
  - approvals
  - safety_events
  - audit_logs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    # --- decision_types ----------------------------------------------------
    op.create_table(
        "decision_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.UniqueConstraint("org_id", "code", name="uq_decision_types_org_code"),
        schema=schema,
    )

    # --- agents ------------------------------------------------------------
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column(
            "model_id",
            sa.String(100),
            nullable=False,
            server_default="gemini-2.0-flash",
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="active"
        ),
        sa.Column(
            "max_tokens_per_call",
            sa.Integer(),
            nullable=False,
            server_default="1000",
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
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
        schema=schema,
    )

    # --- agent_policies ----------------------------------------------------
    op.create_table(
        "agent_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("policy_type", sa.String(20), nullable=False),
        sa.Column("action_pattern", sa.String(500), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        schema=schema,
    )

    # --- preapprovals ------------------------------------------------------
    op.create_table(
        "preapprovals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("conditions", JSONB(), nullable=True),
        sa.Column("applicable_agent_types", ARRAY(sa.String()), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        schema=schema,
    )

    # --- sessions ----------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("decision_type_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_type", sa.String(20), nullable=False, server_default="Human"
        ),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="draft"
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
        schema=schema,
    )
    op.create_index(
        "ix_sessions_org_id", "sessions", ["org_id"], schema=schema
    )
    op.create_index(
        "ix_sessions_created_by", "sessions", ["created_by"], schema=schema
    )

    # --- messages (HPCRDTL core) -------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        # H
        sa.Column("history", sa.String(2000), nullable=False),
        # P / C
        sa.Column("pro", JSONB(), nullable=False, server_default="[]"),
        sa.Column("con", JSONB(), nullable=False, server_default="[]"),
        # R
        sa.Column("recommendation", sa.String(1000), nullable=False),
        # D
        sa.Column("decision", sa.String(1000), nullable=True),
        sa.Column("decision_by", UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        # L
        sa.Column("log", sa.String(500), nullable=True),
        # Agent governance
        sa.Column(
            "actor_type", sa.String(20), nullable=False, server_default="Human"
        ),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("relevant_preapproval_id", UUID(as_uuid=True), nullable=True),
        # Risk & Confidence
        sa.Column("decision_type", sa.String(50), nullable=True),
        sa.Column(
            "risk_score", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column("risk_category", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "response_confidence_score",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "response_confidence_level",
            sa.String(30),
            nullable=False,
            server_default="low",
        ),
        sa.Column(
            "response_confidence_limiting_factors",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
        # Guardrail results
        sa.Column("input_guardrail_result", sa.String(10), nullable=True),
        sa.Column("input_guardrail_detail", JSONB(), nullable=True),
        sa.Column("output_guardrail_result", sa.String(10), nullable=True),
        sa.Column("output_guardrail_detail", JSONB(), nullable=True),
        # Raw AI (internal only)
        sa.Column("raw_ai_response", JSONB(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
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
        # Volume CHECK constraints
        sa.CheckConstraint(
            "char_length(history) <= 2000", name="chk_messages_history_len"
        ),
        sa.CheckConstraint(
            "char_length(recommendation) <= 1000",
            name="chk_messages_recommendation_len",
        ),
        sa.CheckConstraint(
            "char_length(decision) <= 1000", name="chk_messages_decision_len"
        ),
        sa.CheckConstraint(
            "log IS NULL OR char_length(log) <= 500", name="chk_messages_log_len"
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="chk_messages_risk_score_range",
        ),
        sa.CheckConstraint(
            "response_confidence_score >= 0 AND response_confidence_score <= 100",
            name="chk_messages_confidence_range",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_messages_session_id", "messages", ["session_id"], schema=schema
    )

    # --- approvals ---------------------------------------------------------
    op.create_table(
        "approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "level", sa.SmallInteger(), nullable=False, server_default="1"
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
        schema=schema,
    )
    op.create_index(
        "ix_approvals_approver_id", "approvals", ["approver_id"], schema=schema
    )
    op.create_index(
        "ix_approvals_status", "approvals", ["status"], schema=schema
    )

    # --- safety_events (append only) ---------------------------------------
    op.create_table(
        "safety_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "severity", sa.String(10), nullable=False, server_default="medium"
        ),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema=schema,
    )
    op.create_index(
        "ix_safety_events_org_id", "safety_events", ["org_id"], schema=schema
    )
    op.create_index(
        "ix_safety_events_occurred_at",
        "safety_events",
        ["occurred_at"],
        schema=schema,
    )

    # --- audit_logs (append only) -----------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_type", sa.String(20), nullable=False, server_default="human"
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("before_state", JSONB(), nullable=True),
        sa.Column("after_state", JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        schema=schema,
    )
    op.create_index(
        "ix_audit_logs_org_id", "audit_logs", ["org_id"], schema=schema
    )
    op.create_index(
        "ix_audit_logs_occurred_at",
        "audit_logs",
        ["occurred_at"],
        schema=schema,
    )
    op.create_index(
        "ix_audit_logs_actor_id", "audit_logs", ["actor_id"], schema=schema
    )


def downgrade() -> None:
    schema = _schema()
    for table in [
        "audit_logs",
        "safety_events",
        "approvals",
        "messages",
        "sessions",
        "preapprovals",
        "agent_policies",
        "agents",
        "decision_types",
    ]:
        op.drop_table(table, schema=schema)
