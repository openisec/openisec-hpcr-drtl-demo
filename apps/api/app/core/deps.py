from typing import Optional
from fastapi import Depends, HTTPException, Cookie, Header, status
from sqlalchemy.orm import Session
from app.core.database import get_db, set_schema
from app.core.security import decode_access_token
from app.models.public_models import User, LoginSession, Organization
from datetime import datetime, timezone

def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
    if not authorization or not authorization.startswith("Bearer "):
        raise credentials_exception

    access_token = authorization.split(" ", 1)[1]
    payload = decode_access_token(access_token)
    if not payload:
        raise credentials_exception

    session_id = payload.get("session_id")
    user_id = payload.get("sub")
    if not session_id or not user_id:
        raise credentials_exception

    login_session = db.query(LoginSession).filter(
        LoginSession.id == session_id,
        LoginSession.revoked_at == None,
        LoginSession.expires_at > datetime.now(timezone.utc),
    ).first()
    if not login_session:
        raise credentials_exception

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True,
    ).first()
    if not user:
        raise credentials_exception
    return user

def get_org_db(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    set_schema(db, "public")
    return db, current_user, None