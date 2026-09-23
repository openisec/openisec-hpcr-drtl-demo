import logging
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db, tenant_schema, schema_exists
from app.core.provisioning import provision_org_schema
from datetime import datetime, timezone, timedelta
from app.core.security import decode_access_token
from app.models.public_models import User, LoginSession, Organization, UserOrgMembership

logger = logging.getLogger("openisec.deps")

_AUTH_ERROR_MESSAGE = "\u8a8d\u8a3c\u3055\u308c\u3066\u3044\u307e\u305b\u3093"
_ORG_NOT_FOUND_MESSAGE = "\u7d44\u7e54\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093"
_NO_MEMBERSHIP_MESSAGE = "\u3053\u306e\u7d44\u7e54\u3078\u306e\u30a2\u30af\u30bb\u30b9\u6a29\u9650\u304c\u3042\u308a\u307e\u305b\u3093"
_ORG_SETUP_ERROR_MESSAGE = (
    "\u7d44\u7e54\u306e\u521d\u671f\u8a2d\u5b9a\u306b\u554f\u984c\u304c\u3042\u308a\u307e\u3059\u3002"
    "\u7ba1\u7406\u8005\u3078\u3054\u9023\u7d61\u304f\u3060\u3055\u3044\u3002"
)
IDLE_TIMEOUT = timedelta(minutes=30)
ABSOLUTE_SESSION_MAX = timedelta(hours=12)
EXTEND_THROTTLE = timedelta(minutes=5)

ACCESS_TOKEN_COOKIE_NAME = "access_token"


def get_current_session_and_user(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[LoginSession, User]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_AUTH_ERROR_MESSAGE,
    )
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if not access_token:
        raise credentials_exception
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

    # スライディング有効期限(アイドル30分・絶対上限12時間)
    now = datetime.now(timezone.utc)
    new_expiry = min(
        now + IDLE_TIMEOUT,
        login_session.created_at + ABSOLUTE_SESSION_MAX,
    )
    if new_expiry - login_session.expires_at > EXTEND_THROTTLE:
        login_session.expires_at = new_expiry
        db.commit()

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True,
    ).first()
    if not user:
        raise credentials_exception
    return login_session, user


def get_current_user(
    session_and_user: tuple[LoginSession, User] = Depends(get_current_session_and_user),
) -> User:
    _, user = session_and_user
    return user


def get_org_db(
    session_and_user: tuple[LoginSession, User] = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
):
    """
    Switches search_path to the session's active organization schema,
    scoped to the request's transaction (SET LOCAL). Reverts
    automatically to public when this generator's block exits.

    active_org_id follows the session (set via /auth/switch-org), not
    the JWT, so a switch takes effect immediately without reissuing
    the token. Falls back to the user's home organization_id when the
    session hasn't switched away from it (active_org_id is NULL).

    Membership is re-verified on every call (not just at switch time)
    so a revoked membership takes effect immediately too.

    Do NOT reuse this session (db) inside BackgroundTasks or any
    context outside this request's lifecycle. BackgroundTasks must
    obtain a fresh session via get_db() instead.
    """
    login_session, current_user = session_and_user
    target_org_id = login_session.active_org_id or current_user.organization_id

    membership = db.query(UserOrgMembership).filter(
        UserOrgMembership.user_id == current_user.id,
        UserOrgMembership.organization_id == target_org_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail=_NO_MEMBERSHIP_MESSAGE)

    org = db.query(Organization).filter(Organization.id == target_org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail=_ORG_NOT_FOUND_MESSAGE)

    # 自己修復: organizations レコードはあるが、テナントスキーマ本体が
    # 存在しない(過去の登録処理の失敗等で孤立した)場合、その場で
    # provision_org_schema() を再実行して補完を試みる。
    # provision_org_schema() は各ステップが冪等なため、既に正常な
    # 組織に対して呼んでも安全(無害な no-op)。
    if not schema_exists(db, org.pg_schema):
        logger.warning(
            "Tenant schema missing for org_id=%s pg_schema=%s; "
            "attempting self-heal via provision_org_schema()",
            org.id, org.pg_schema,
        )
        try:
            provision_org_schema(org.pg_schema)
        except Exception:
            logger.exception(
                "Self-heal failed for org_id=%s pg_schema=%s",
                org.id, org.pg_schema,
            )
            raise HTTPException(status_code=503, detail=_ORG_SETUP_ERROR_MESSAGE)
        logger.info(
            "Self-heal succeeded for org_id=%s pg_schema=%s",
            org.id, org.pg_schema,
        )

    with tenant_schema(db, org.pg_schema):
        yield db, current_user, org