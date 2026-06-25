import json
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_org_db
from app.core.security import validate_input, mask_pii
from app.models.org_models import Session as OrgSession, Message, AuditLog
from app.models.public_models import User
from app.services.gemini_service import analyze_with_gemini

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class MessageRequest(BaseModel):
    query: str
    history_context: Optional[str] = None
    decision_type: Optional[str] = None


class DecisionRequest(BaseModel):
    decision: str
    reason: Optional[str] = None
    target_date: Optional[str] = None  # ISO format: YYYY-MM-DD


class MessageResponse(BaseModel):
    id: str
    session_id: str
    history: Optional[str] = None
    pro: Optional[list] = None
    con: Optional[list] = None
    recommendation: Optional[str] = None
    decision: Optional[str] = None
    risk_score: int = 0
    risk_category: list = []
    response_confidence_score: int = 0
    response_confidence_level: str = "low"
    response_confidence_limiting_factors: list = []
    log: Optional[str] = None
    status: str
    created_at: str


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/messages
# ---------------------------------------------------------------------------
@router.post("/sessions/{session_id}/messages", status_code=201)
async def create_message(
    session_id: uuid.UUID,
    payload: MessageRequest,
    org_db=Depends(get_org_db),
):
    db, current_user, _ = org_db

    # Validate session
    session = db.query(OrgSession).filter(
        OrgSession.id == session_id,
        OrgSession.created_by == current_user.id,
        OrgSession.status.in_(["draft", "open"]),
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or closed")

    # Input Guardrail (LLM01/LLM04)
    is_valid, reason = validate_input(payload.query)
    if not is_valid:
        raise HTTPException(status_code=422, detail=f"Input validation failed: {reason}")

    # PII masking before sending to AI (LLM02)
    safe_query = mask_pii(payload.query)
    safe_history = mask_pii(payload.history_context) if payload.history_context else None

    # Create message record with placeholder values
    msg = Message(
        id=uuid.uuid4(),
        session_id=session.id,
        query=payload.query,
        history="",
        pro=[],
        con=[],
        recommendation="",
        risk_score=0,
        risk_category=[],
        response_confidence_score=0,
        response_confidence_level="low",
        response_confidence_limiting_factors=[],
        actor_type="Human",
        decision_type=payload.decision_type,
    )
    # Update session status to open
    session.status = "open"
    db.add(session)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    try:
        # Call Gemini Flash (LLM05: output validated in service)
        hpcr_drtl = await analyze_with_gemini(
            query=safe_query,
            history_context=safe_history,
            decision_type=payload.decision_type,
        )

        # Map Gemini output to Message model fields
        confidence = hpcr_drtl.get("response_confidence", {})
        log_summary = (
            f"Query analyzed. Risk: {hpcr_drtl.get('risk_score', 0)}/100. "
            f"Confidence: {confidence.get('level', 'unknown')}. "
            f"Auto-generated at {datetime.now(timezone.utc).isoformat()}"
        )[:500]

        msg.history = hpcr_drtl.get("history", "")
        msg.pro = hpcr_drtl.get("pro", [])
        msg.con = hpcr_drtl.get("con", [])
        msg.recommendation = hpcr_drtl.get("recommendation", "")
        msg.risk_score = hpcr_drtl.get("risk_score", 0)
        msg.risk_category = hpcr_drtl.get("risk_category", [])
        msg.response_confidence_score = confidence.get("score", 0)
        msg.response_confidence_level = confidence.get("level", "low")
        msg.response_confidence_limiting_factors = confidence.get("limiting_factors", [])
        msg.log = log_summary

        db.commit()
        db.refresh(msg)

    except Exception as e:
        db.delete(msg)
        db.commit()
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)[:200]}")

    return {
        "id": str(msg.id),
        "query": msg.query,
        "session_id": str(msg.session_id),
        "history": msg.history,
        "pro": msg.pro,
        "con": msg.con,
        "recommendation": msg.recommendation,
        "decision": msg.decision,
        "risk_score": msg.risk_score,
        "risk_category": msg.risk_category,
        "response_confidence_score": msg.response_confidence_score,
        "response_confidence_level": msg.response_confidence_level,
        "response_confidence_limiting_factors": msg.response_confidence_limiting_factors,
        "log": msg.log,
        "status": "awaiting_decision",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/messages/{message_id}/decision
# ---------------------------------------------------------------------------
@router.post("/sessions/{session_id}/messages/{message_id}/decision", status_code=200)
def record_decision(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: DecisionRequest,
    org_db=Depends(get_org_db),
):
    db, current_user, _ = org_db

    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.session_id == session_id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.decision = payload.decision[:1000]
    msg.reason = payload.reason[:2000] if payload.reason else None
    msg.decision_by = current_user.id
    msg.decided_at = datetime.now(timezone.utc)
    if payload.target_date:
        msg.target_date = date.fromisoformat(payload.target_date)

    # Update session status to closed
    sess = db.query(OrgSession).filter(OrgSession.id == session_id).first()
    if sess:
        sess.status = "closed"

    db.commit()
    db.refresh(msg)

    return {
        "id": str(msg.id),
        "decision": msg.decision,
        "reason": msg.reason,
        "target_date": msg.target_date.isoformat() if msg.target_date else None,
        "decided_at": msg.decided_at.isoformat(),
        "message": "Decision recorded successfully",
    }