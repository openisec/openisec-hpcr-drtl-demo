import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.core.deps import get_org_db
from app.models.public_models import User
from app.models.org_models import Session as OrgSession, DecisionType
from app.schemas.session import SessionCreate, SessionResponse
from datetime import datetime, timezone

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(
    payload: SessionCreate,
    ctx=Depends(get_org_db),
):
    db, current_user, org = ctx

    # Validate decision_type_id if provided
    if payload.decision_type_id:
        dt = db.query(DecisionType).filter(
            DecisionType.id == payload.decision_type_id,
            DecisionType.is_active == True,
        ).first()
        if not dt:
            raise HTTPException(status_code=404, detail="Decision type not found")

    session = OrgSession(
        id=uuid.uuid4(),
        org_id=current_user.organization_id,
        created_by=current_user.id,
        title=payload.title,
        status="draft",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionResponse(
        id=str(session.id),
        title=session.title,
        status=session.status,
        created_at=session.created_at,
    )


@router.get("", response_model=list[SessionResponse])
def list_sessions(ctx=Depends(get_org_db)):
    db, current_user, org = ctx

    sessions = db.query(OrgSession).filter(
        OrgSession.created_by == current_user.id,
    ).order_by(OrgSession.created_at.desc()).limit(50).all()

    return [
        SessionResponse(
            id=str(s.id),
            title=s.title,
            status=s.status,
            created_at=s.created_at,
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, ctx=Depends(get_org_db)):
    db, current_user, org = ctx

    session = db.query(OrgSession).filter(
        OrgSession.id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        id=str(session.id),
        title=session.title,
        status=session.status,
        created_at=session.created_at,
    )
