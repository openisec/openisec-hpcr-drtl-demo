import hashlib
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password,
    create_access_token, generate_token
)
from app.core.deps import get_current_user
from app.models.public_models import User, Organization, LoginSession
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(
        id=uuid.uuid4(),
        name=payload.organization_name,
        domain=f"{payload.organization_name.lower().replace(' ', '-')}.local",
        pg_schema=f"org_{str(uuid.uuid4()).replace('-', '_')}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(org)
    db.flush()

    user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role="admin",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        organization_id=str(user.organization_id),
        message="Registration successful",
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.email == payload.email,
        User.is_active == True,
    ).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    raw_token = generate_token()
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    session = LoginSession(
        id=uuid.uuid4(),
        user_id=user.id,
        session_token_hash=token_hash,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()

    token = create_access_token(
        subject=str(user.id),
        extra={"session_id": str(session.id)},
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "organization_id": str(user.organization_id),
        "message": "Login successful",
    }


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(LoginSession).filter(
        LoginSession.user_id == current_user.id,
    ).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "organization_id": str(current_user.organization_id),
    }