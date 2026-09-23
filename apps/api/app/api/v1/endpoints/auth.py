import hashlib
import logging
import secrets as pysecrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password,
    create_access_token, generate_token, generate_temp_password,
    decode_access_token,
)
from app.core.deps import get_current_user, get_current_session_and_user, ACCESS_TOKEN_COOKIE_NAME  # ACCESS_TOKEN_COOKIE_NAMEを追加import
from app.core.provisioning import provision_org_schema
from app.core.audit import record_auth_audit_log, AuthAuditAction, get_client_ip, get_client_user_agent, record_audit_log, record_tenant_audit_log, OrgAuditAction
from app.models.public_models import (
    User, Organization, LoginSession, AuthToken, UserOrgMembership,
    EmailVerificationToken,
)
from app.schemas.auth import (
    RegisterRequest, LoginRequest, AuthResponse,
    PasswordResetRequest, PasswordResetConfirm, MessageResponse,
    LoginResponse, MembershipInfo, SwitchOrgRequest, SwitchOrgResponse,
    MeResponse, MemberCreateRequest, MemberCreateResponse,
    UserMeResponse, PasswordChangeRequest, PasswordChangeResponse,
    MemberListItem, MemberListResponse,
    MemberUpdateRequest, MemberUpdateResponse, ReissueTempPasswordResponse,
    OrganizationListItem, OrganizationListResponse,
    NameUpdateRequest, NameUpdateResponse,
    OrganizationCreateRequest, OrganizationCreateResponse,
    OrganizationUpdateRequest, OrganizationUpdateResponse,
    PreRegisterRequest, VerifyEmailResponse,
)
from app.services.mail_service import send_password_reset_email, send_verification_email
from app.core.rate_limit import limiter
from app.core.config import get_settings as _get_settings_rl

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = logging.getLogger("openisec.auth")

PERSONAL_ORG_NAMES = {"個人", "personal"}


def _get_valid_verification_token(
    db: Session, token: str, for_update: bool = False
) -> EmailVerificationToken | None:
    """
    Return the EmailVerificationToken row matching the raw token, if it is
    unconsumed and unexpired. Shared by verify_email (read-only check) and
    register (which additionally locks + consumes the row).

    for_update=True issues SELECT ... FOR UPDATE so that concurrent
    requests using the same token serialize on this row: the second
    request only proceeds after the first's transaction commits, by which
    point consumed_at is already set and the filter no longer matches.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    query = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == token_hash,
        EmailVerificationToken.consumed_at.is_(None),
        EmailVerificationToken.expires_at > datetime.now(timezone.utc),
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit(f"{settings.AUTH_RATE_LIMIT_PER_MINUTE}/minute")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="このメールアドレスは既に登録されています")

    # トークン検証と消費(行ロック付き)。
    # 同一トークンでの同時リクエストは、片方がここでブロックされ、
    # 先行トランザクションのcommit後に再評価されると consumed_at が
    # 既に埋まっているため無効トークン扱いとなり、二重登録を防げる。
    # 消費(consumed_at確定+commit)は、後続の組織作成/user作成の成否に
    # 関わらずここで確定する(折衷案)。組織作成以降で失敗した場合、
    # トークンは使用済みのまま残るため、ユーザーは pre-register から
    # やり直す必要がある(既知のトレードオフ。組織名衝突の救済は別課題)。
    verification_token = _get_valid_verification_token(db, payload.token, for_update=True)
    if not verification_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="リンクが無効か、有効期限が切れています",
        )
    if verification_token.email != payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="リンクが無効か、有効期限が切れています",
        )

    verification_token.consumed_at = datetime.now(timezone.utc)
    db.commit()

    org_name = payload.organization_name.strip()
    is_personal = org_name.lower() in PERSONAL_ORG_NAMES

    if is_personal:
        domain = f"personal-{uuid.uuid4()}.local"
    else:
        existing_org = db.query(Organization).filter(
            func.lower(Organization.name) == org_name.lower()
        ).first()
        if existing_org:
            raise HTTPException(
                status_code=409,
                detail="組織名が既に登録されています。その組織メンバーに参加されたい場合は、組織の管理者またはOpenisecのAdminへご連絡ください。",
            )
        domain = f"{org_name.lower().replace(' ', '-')}.local"

    org = Organization(
        id=uuid.uuid4(),
        name=org_name,
        domain=domain,
        pg_schema=f"org_{str(uuid.uuid4()).replace('-', '_')}",
        is_personal=is_personal,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(org)
    # organizations レコードを先に確定コミットする。
    # provision_org_schema() は Alembic 経由で別コネクションを使い、
    # その場でコミットしてしまうため、org の確定を後回しにすると
    # 「スキーマだけ存在し organizations レコードが無い」孤立状態を
    # 生みやすい。順序を入れ替えることで、万一この後の処理が失敗しても
    # 「organizations レコードはあるがスキーマが未完成」という、
    # get_org_db の自己修復(schema_exists + provision_org_schema 再実行)
    # で回復可能な状態に留める。
    db.commit()
    db.refresh(org)

    try:
        provision_org_schema(org.pg_schema)
    except Exception:
        logger.exception(
            "provision_org_schema failed during registration: org_id=%s pg_schema=%s",
            org.id, org.pg_schema,
        )
        raise HTTPException(
            status_code=503,
            detail="組織は作成されましたが、初期設定に失敗しました。管理者へご連絡ください。",
        )

    now = datetime.now(timezone.utc)
    client_ip = get_client_ip(request)
    client_ua = get_client_user_agent(request)

    user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        family_name=payload.family_name,
        given_name=payload.given_name,
        # 個人/Personal組織は一人組織のため、管理者・承認者である
        # 必要がなく、デフォルトロールはmemberとする。それ以外の
        # 組織(複数人が所属しうる)は、登録者が組織の最初のメンバー
        # となるためadminのままとする。
        role="member" if is_personal else "admin",
        is_active=True,
        # このユーザー自身の個人組織として恒久的に紐付ける(組織変更後も
        # 元の個人組織を特定できるようにするため。update_member 参照)。
        personal_org_id=org.id if is_personal else None,
        terms_version=settings.TERMS_VERSION,
        privacy_policy_version=settings.PRIVACY_POLICY_VERSION,
        agreed_terms_at=now,
        agreed_privacy_at=now,
        marketing_opt_in=payload.marketing_opt_in,
        marketing_opt_in_at=now if payload.marketing_opt_in else None,
        ip_address=client_ip,
        user_agent=client_ua,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 新規登録者を自身の組織のメンバーとして登録する。
    # これが無いと /auth/switch-org や get_current_session_and_user
    # 経由の組織アクセスチェックが全て失敗し、ログイン後に
    # 「この組織へのアクセス権限がありません」となってしまう。
    membership = UserOrgMembership(
        id=uuid.uuid4(),
        user_id=user.id,
        organization_id=org.id,
        role=user.role,
    )
    db.add(membership)
    record_auth_audit_log(
        db,
        action=AuthAuditAction.EMAIL_VERIFIED,
        actor_id=user.id,
        actor_email=user.email,
        org_id=org.id,
        request=request,
    )
    db.commit()

    return AuthResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        organization_id=str(user.organization_id),
        message="登録が完了しました",
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit(f"{settings.AUTH_RATE_LIMIT_PER_MINUTE}/minute")
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.email == payload.email,
        User.is_active == True,
    ).first()

    if not user or not verify_password(payload.password, user.password_hash):
        # ログイン失敗も記録する。存在しないメールアドレスの場合は
        # actor_id を残さず、入力されたメールアドレスのみ記録する
        # (アカウント列挙攻撃の手がかりを増やさないよう、成功/失敗で
        # レスポンス自体は変えない)。
        record_auth_audit_log(
            db,
            action=AuthAuditAction.LOGIN_FAILURE,
            actor_id=user.id if user else None,
            actor_email=payload.email,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
        )

    raw_token = generate_token()
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    session = LoginSession(
        id=uuid.uuid4(),
        user_id=user.id,
        session_token_hash=token_hash,
        # 前回スイッチしていた組織を引き継ぐ(無ければホーム組織)。
        # これによりログインし直しても意図せずホーム組織へ戻らない。
        active_org_id=user.last_active_org_id or user.organization_id,
        ip_address=get_client_ip(request),
        user_agent=get_client_user_agent(request),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    record_auth_audit_log(
        db,
        action=AuthAuditAction.LOGIN_SUCCESS,
        actor_id=user.id,
        actor_email=user.email,
        org_id=session.active_org_id,
        request=request,
    )
    db.commit()

    token = create_access_token(
        subject=str(user.id),
        extra={"session_id": str(session.id)},
    )

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        max_age=43200,
        path="/",
    )

    membership_rows = (
        db.query(UserOrgMembership, Organization)
        .join(Organization, Organization.id == UserOrgMembership.organization_id)
        .filter(UserOrgMembership.user_id == user.id)
        .all()
    )
    memberships = [
        MembershipInfo(
            organization_id=str(membership.organization_id),
            organization_name=org.name,
            role=membership.role,
        )
        for membership, org in membership_rows
    ]

    return LoginResponse(
        # access_token=token を削除(Cookieに移行したため)
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        organization_id=str(user.organization_id),
        is_platform_admin=user.is_platform_admin,
        memberships=memberships,
        message="ログインしました",
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,  # Cookie削除のため追加
    db: Session = Depends(get_db),
):
    """
    ログアウト。有効なセッションが見つかればDB上で失効させ監査ログに
    記録するが、Cookie自体は常に削除し、常に成功レスポンスを返す
    (ベストエフォート)。get_current_session_and_user に依存すると、
    アイドルタイムアウト等でセッションが既に無効な場合に401となり、
    ブラウザ側のローカル状態はクリアされていてもAPI呼び出しだけが
    失敗する非対称な状態になるため、logoutに限りこの依存を外している。
    """
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if access_token:
        payload = decode_access_token(access_token)
        if payload:
            session_id = payload.get("session_id")
            user_id = payload.get("sub")
            if session_id and user_id:
                login_session = db.query(LoginSession).filter(
                    LoginSession.id == session_id,
                    LoginSession.revoked_at.is_(None),
                ).first()
                if login_session:
                    current_user = db.query(User).filter(User.id == user_id).first()
                    if current_user:
                        active_org_id = login_session.active_org_id or current_user.organization_id
                        login_session.revoked_at = datetime.now(timezone.utc)
                        record_auth_audit_log(
                            db,
                            action=AuthAuditAction.LOGOUT,
                            actor_id=current_user.id,
                            actor_email=current_user.email,
                            org_id=active_org_id,
                            request=request,
                        )
                        db.commit()

    # Cookie削除(セッションの有効/無効に関わらず必ず実行)
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    return {"message": "ログアウトしました"}


_NO_MEMBERSHIP_MESSAGE = "\u3053\u306e\u7d44\u7e54\u3078\u306e\u30a2\u30af\u30bb\u30b9\u6a29\u9650\u304c\u3042\u308a\u307e\u305b\u3093"
_ORG_NOT_FOUND_MESSAGE = "\u7d44\u7e54\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093"
_NOT_AUTHORIZED_MESSAGE = "\u3053\u306e\u64cd\u4f5c\u3092\u884c\u3046\u6a29\u9650\u304c\u3042\u308a\u307e\u305b\u3093"
_EMAIL_EXISTS_MESSAGE = "\u3053\u306e\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306f\u65e2\u306b\u767b\u9332\u3055\u308c\u3066\u3044\u307e\u3059"


def _require_org_admin(current_user: User, target_org_id, db: Session) -> None:
    """
    Raise 403 unless current_user is a platform admin, or holds the
    "admin" role in target_org_id via UserOrgMembership.
    """
    if current_user.is_platform_admin:
        return
    membership = db.query(UserOrgMembership).filter(
        UserOrgMembership.user_id == current_user.id,
        UserOrgMembership.organization_id == target_org_id,
        UserOrgMembership.role == "admin",
    ).first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_NOT_AUTHORIZED_MESSAGE,
        )


@router.post("/switch-org", response_model=SwitchOrgResponse)
def switch_org(
    payload: SwitchOrgRequest,
    request: Request,
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
):
    """
    組織スイッチはガバナンス統制として、自分自身をその組織の"admin"として
    membershipに追加している場合のみ許可する(platform_adminであっても
    例外なし)。安易な他組織閲覧を防ぐための"縛り"であり、加えて実行の都度
    パスワード再確認を必須とする。切替元(switch_out)・切替先の成否
    (switch_in_success / switch_in_failure)をそれぞれ監査ログに記録する。
    """
    login_session, current_user = session_and_user
    from_org_id = login_session.active_org_id or current_user.organization_id

    membership = db.query(UserOrgMembership).filter(
        UserOrgMembership.user_id == current_user.id,
        UserOrgMembership.organization_id == payload.organization_id,
        UserOrgMembership.role == "admin",
    ).first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_NO_MEMBERSHIP_MESSAGE,
        )

    org = db.query(Organization).filter(Organization.id == payload.organization_id).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_ORG_NOT_FOUND_MESSAGE,
        )

    # switch_outは「切り替えの試み」自体を示すログとして、パスワード確認の
    # 成否に関わらず先に記録する(失敗してもどの組織から離れようとしたかは
    # 監査上残す)。
    record_auth_audit_log(
        db,
        action=AuthAuditAction.SWITCH_OUT,
        actor_id=current_user.id,
        actor_email=current_user.email,
        org_id=from_org_id,
        request=request,
    )

    if not verify_password(payload.password, current_user.password_hash):
        record_auth_audit_log(
            db,
            action=AuthAuditAction.SWITCH_IN_FAILURE,
            actor_id=current_user.id,
            actor_email=current_user.email,
            org_id=org.id,
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="パスワードが正しくありません",
        )

    login_session.active_org_id = org.id
    current_user.last_active_org_id = org.id

    record_auth_audit_log(
        db,
        action=AuthAuditAction.SWITCH_IN_SUCCESS,
        actor_id=current_user.id,
        actor_email=current_user.email,
        org_id=org.id,
        request=request,
    )
    db.commit()

    return SwitchOrgResponse(
        organization_id=str(org.id),
        organization_name=org.name,
        role=membership.role,
    )


@router.get("/me", response_model=UserMeResponse)
def me(
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
):
    login_session, current_user = session_and_user
    active_org_id = login_session.active_org_id or current_user.organization_id

    membership_rows = (
        db.query(UserOrgMembership, Organization)
        .join(Organization, Organization.id == UserOrgMembership.organization_id)
        .filter(UserOrgMembership.user_id == current_user.id)
        .all()
    )
    memberships = [
        MembershipInfo(
            organization_id=str(membership.organization_id),
            organization_name=org.name,
            role=membership.role,
        )
        for membership, org in membership_rows
    ]

    return UserMeResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        is_platform_admin=current_user.is_platform_admin,
        must_change_password=current_user.must_change_password,
        memberships=memberships,
        active_org_id=str(active_org_id) if active_org_id else None,
    )


@router.patch("/me", response_model=NameUpdateResponse)
def update_my_name(
    payload: NameUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    C. 個人アカウントページ: 本人による氏名変更。
    組織メンバー管理(update_member)とは別の、常に「自分自身」のみを
    対象とするエンドポイント。
    """
    current_user.family_name = payload.family_name
    current_user.given_name = payload.given_name
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_user)

    return NameUpdateResponse(full_name=current_user.full_name)


def _build_reset_token(db: Session, user: User) -> str:
    """Create a single-use password_reset AuthToken and return the raw token."""
    raw_token = pysecrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    auth_token = AuthToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        purpose="password_reset",
        expires_at=datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        ),
        created_at=datetime.now(timezone.utc),
    )
    db.add(auth_token)
    db.commit()
    return raw_token


@router.post("/password-reset/request", response_model=MessageResponse)
@limiter.limit(f"{settings.AUTH_RATE_LIMIT_PER_MINUTE}/minute")
async def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Always returns the same generic message regardless of whether the
    email exists, to prevent user enumeration.
    """
    generic_message = MessageResponse(
        message="登録されているメールアドレスの場合、パスワード再設定用のリンクをお送りしました"
    )

    user = db.query(User).filter(
        User.email == payload.email,
        User.is_active == True,
    ).first()

    if not user:
        return generic_message

    raw_token = _build_reset_token(db, user)
    reset_url = f"{settings.FRONTEND_URL}/password-reset/confirm?token={raw_token}"

    background_tasks.add_task(send_password_reset_email, user.email, reset_url)

    return generic_message


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    auth_token = db.query(AuthToken).filter(
        AuthToken.token_hash == token_hash,
        AuthToken.purpose == "password_reset",
        AuthToken.used_at.is_(None),
        AuthToken.expires_at > datetime.now(timezone.utc),
    ).first()

    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="リンクが無効か、有効期限が切れています",
        )

    user = db.query(User).filter(User.id == auth_token.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="リンクが無効か、有効期限が切れています",
        )

    user.password_hash = hash_password(payload.new_password)
    auth_token.used_at = datetime.now(timezone.utc)

    # Revoke all existing sessions on password change
    db.query(LoginSession).filter(
        LoginSession.user_id == user.id,
        LoginSession.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc)})

    db.commit()

    return MessageResponse(message="パスワードを再設定しました")


@router.post("/change-password", response_model=PasswordChangeResponse)
def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="現在のパスワードが正しくありません",
        )

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return PasswordChangeResponse()


@router.get("/organizations", response_model=OrganizationListResponse)
def list_organizations(
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
):
    """
    Platform admin: 全組織を返す(組織管理画面・リスクスコア閾値設定の一覧用)。
    組織admin: 自組織の1件のみ返す(リスクスコア閾値設定で自組織の行を
    表示・変更するため)。admin未満のロールは403。
    """
    login_session, current_user = session_and_user

    if current_user.is_platform_admin:
        orgs = db.query(Organization).order_by(Organization.name).all()
    else:
        target_org_id = login_session.active_org_id or current_user.organization_id
        _require_org_admin(current_user, target_org_id, db)
        orgs = db.query(Organization).filter(Organization.id == target_org_id).all()

    return OrganizationListResponse(
        organizations=[
            OrganizationListItem(
                id=str(o.id),
                name=o.name,
                is_active=o.is_active,
                risk_score_threshold=o.risk_score_threshold,
                is_personal=o.is_personal,
            )
            for o in orgs
        ]
    )


@router.patch("/organizations/{org_id}", response_model=OrganizationUpdateResponse)
def update_organization(
    org_id: str,
    payload: OrganizationUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    E. 「管理設定」からの組織更新。
    - risk_score_threshold: 組織admin(自組織のみ)/Platform adminが変更可
    - name / is_active: Platform adminのみ変更可
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ORG_NOT_FOUND_MESSAGE)

    _require_org_admin(current_user, org_id, db)

    if payload.name is not None or payload.is_active is not None:
        if not current_user.is_platform_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_AUTHORIZED_MESSAGE)

    if payload.name is not None:
        existing_org = db.query(Organization).filter(
            func.lower(Organization.name) == payload.name.lower(),
            Organization.id != org.id,
        ).first()
        if existing_org:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="同名の組織が既に存在します",
            )
        org.name = payload.name

    if payload.is_active is not None:
        org.is_active = payload.is_active

    if payload.risk_score_threshold is not None and payload.risk_score_threshold != org.risk_score_threshold:
        old_threshold = org.risk_score_threshold
        org.risk_score_threshold = payload.risk_score_threshold

        record_tenant_audit_log(
            db,
            org,
            action=OrgAuditAction.RISK_THRESHOLD_CHANGED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="organization",
            resource_id=org.id,
            before_state={"risk_score_threshold": old_threshold},
            after_state={"risk_score_threshold": org.risk_score_threshold},
            request=request,
        )

    org.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(org)

    return OrganizationUpdateResponse(
        id=str(org.id),
        name=org.name,
        is_active=org.is_active,
        risk_score_threshold=org.risk_score_threshold,
    )


@router.post("/organizations", response_model=OrganizationCreateResponse, status_code=201)
def create_organization(
    payload: OrganizationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Platform adminによる組織の箱だけの作成。メンバーは後から
    /auth/members (create_member) で追加する想定。register() と
    同様、organizationsレコードのコミットを先に確定させてから
    provision_org_schema() を呼ぶことで、途中失敗時も get_org_db の
    自己修復で回復可能な状態に留める。
    """
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_AUTHORIZED_MESSAGE)

    org_name = payload.name.strip()

    existing_org = db.query(Organization).filter(
        func.lower(Organization.name) == org_name.lower()
    ).first()
    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同名の組織が既に存在します",
        )

    org = Organization(
        id=uuid.uuid4(),
        name=org_name,
        domain=f"{org_name.lower().replace(' ', '-')}.local",
        pg_schema=f"org_{str(uuid.uuid4()).replace('-', '_')}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    try:
        provision_org_schema(org.pg_schema)
    except Exception:
        logger.exception(
            "provision_org_schema failed during org creation by platform admin: org_id=%s pg_schema=%s",
            org.id, org.pg_schema,
        )
        raise HTTPException(
            status_code=503,
            detail="組織は作成されましたが、初期設定に失敗しました。もう一度お試しいただくか、時間をおいて再度アクセスしてください。",
        )

    return OrganizationCreateResponse(id=str(org.id), name=org.name)


@router.post("/members", response_model=MemberCreateResponse, status_code=201)
def create_member(
    payload: MemberCreateRequest,
    request: Request,
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
):
    login_session, current_user = session_and_user

    if current_user.is_platform_admin and payload.organization_id:
        target_org_id = payload.organization_id
    else:
        target_org_id = login_session.active_org_id or current_user.organization_id

    _require_org_admin(current_user, target_org_id, db)

    org = db.query(Organization).filter(Organization.id == target_org_id).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_ORG_NOT_FOUND_MESSAGE,
        )

    existing_user = db.query(User).filter(User.email == payload.email).first()

    if existing_user:
        already_member = db.query(UserOrgMembership).filter(
            UserOrgMembership.user_id == existing_user.id,
            UserOrgMembership.organization_id == org.id,
        ).first()
        if already_member:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_EMAIL_EXISTS_MESSAGE,
            )

        membership_row = UserOrgMembership(
            id=uuid.uuid4(),
            user_id=existing_user.id,
            organization_id=org.id,
            role=payload.role,
        )
        db.add(membership_row)

        record_tenant_audit_log(
            db,
            org,
            action=OrgAuditAction.MEMBER_CREATED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="member",
            target_user_id=existing_user.id,
            after_state={"email": existing_user.email, "role": payload.role},
            request=request,
        )
        db.commit()

        return MemberCreateResponse(
            user_id=str(existing_user.id),
            email=existing_user.email,
            full_name=existing_user.full_name,
            role=payload.role,
            organization_id=str(org.id),
            temp_password=None,
            message="既存アカウントをこの組織のメンバーとして追加しました。本人は既存のパスワードでログイン後、組織を切り替えてご利用いただけます。",
        )

    temp_password = generate_temp_password()
    now = datetime.now(timezone.utc)

    new_user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=payload.email,
        password_hash=hash_password(temp_password),
        family_name=payload.family_name,
        given_name=payload.given_name,
        role=payload.role,
        is_active=True,
        must_change_password=True,
        created_at=now,
        updated_at=now,
    )
    db.add(new_user)
    db.flush()

    membership_row = UserOrgMembership(
        id=uuid.uuid4(),
        user_id=new_user.id,
        organization_id=org.id,
        role=payload.role,
    )
    db.add(membership_row)

    record_tenant_audit_log(
        db,
        org,
        action=OrgAuditAction.MEMBER_CREATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="member",
        target_user_id=new_user.id,
        after_state={"email": new_user.email, "role": new_user.role},
        request=request,
    )
    db.commit()

    return MemberCreateResponse(
        user_id=str(new_user.id),
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        organization_id=str(org.id),
        temp_password=temp_password,
    )


@router.get("/members", response_model=MemberListResponse)
def list_members(
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
):
    login_session, current_user = session_and_user

    if current_user.is_platform_admin:
        rows = (
            db.query(User, UserOrgMembership, Organization)
            .join(UserOrgMembership, UserOrgMembership.user_id == User.id)
            .join(Organization, Organization.id == UserOrgMembership.organization_id)
            .order_by(Organization.name, User.created_at)
            .all()
        )
    else:
        target_org_id = login_session.active_org_id or current_user.organization_id
        _require_org_admin(current_user, target_org_id, db)
        rows = (
            db.query(User, UserOrgMembership, Organization)
            .join(UserOrgMembership, UserOrgMembership.user_id == User.id)
            .join(Organization, Organization.id == UserOrgMembership.organization_id)
            .filter(UserOrgMembership.organization_id == target_org_id)
            .order_by(User.created_at)
            .all()
        )

    members = [
        MemberListItem(
            user_id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            organization_id=str(org.id),
            organization_name=org.name,
            must_change_password=user.must_change_password,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            personal_org_id=str(user.personal_org_id) if user.personal_org_id else None,
        )
        for user, membership, org in rows
    ]

    return MemberListResponse(members=members)


@router.patch("/organizations/{org_id}/members/{user_id}", response_model=MemberUpdateResponse)
def update_member(
    org_id: str,
    user_id: str,
    payload: MemberUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if str(current_user.id) == user_id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="自分自身を無効化することはできません",
        )

    membership = db.query(UserOrgMembership).filter(
        UserOrgMembership.user_id == user_id,
        UserOrgMembership.organization_id == org_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_MEMBERSHIP_MESSAGE)

    _require_org_admin(current_user, org_id, db)

    org = db.query(Organization).filter(Organization.id == org_id).first()
    target_user = db.query(User).filter(User.id == user_id).first()
    old_role = membership.role

    if payload.new_organization_id is not None:
        if not current_user.is_platform_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_NOT_AUTHORIZED_MESSAGE)
        new_org = db.query(Organization).filter(Organization.id == payload.new_organization_id).first()
        if not new_org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ORG_NOT_FOUND_MESSAGE)
        already_there = db.query(UserOrgMembership).filter(
            UserOrgMembership.user_id == user_id,
            UserOrgMembership.organization_id == new_org.id,
        ).first()
        if already_there:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="対象ユーザーは既に移動先の組織のメンバーです",
            )
        # 「個人」組織は1人専用。対象ユーザー自身の個人組織(personal_org_id)
        # 以外の個人組織へは、誰であってもマッピングできないようにする
        # (複数人が同じ個人組織に紐づいてしまう事故を防ぐ)。
        if new_org.is_personal and str(new_org.id) != str(target_user.personal_org_id or ""):
            own_personal_org_id = str(target_user.personal_org_id) if target_user.personal_org_id else "なし"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"このユーザーの個人の組織IDは'{own_personal_org_id}'です。"
                    "この個人を表す組織ID又は個人以外の組織にのみマッピング可能です"
                ),
            )
        was_home_org = str(target_user.organization_id) == org_id
        membership.organization_id = new_org.id
        if was_home_org:
            target_user.organization_id = new_org.id
            target_user.updated_at = datetime.now(timezone.utc)

        # 異動元(org)と異動先(new_org)、両方のテナントスキーマに記録する。
        record_tenant_audit_log(
            db,
            org,
            action=OrgAuditAction.MEMBER_ORG_MOVED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="member",
            target_user_id=target_user.id,
            before_state={"email": target_user.email, "organization_id": org_id},
            after_state={"email": target_user.email, "organization_id": str(new_org.id)},
            request=request,
        )
        record_tenant_audit_log(
            db,
            new_org,
            action=OrgAuditAction.MEMBER_ORG_MOVED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="member",
            target_user_id=target_user.id,
            before_state={"email": target_user.email, "organization_id": org_id},
            after_state={"email": target_user.email, "organization_id": str(new_org.id)},
            request=request,
        )

    if payload.role is not None and payload.role != old_role:
        membership.role = payload.role
        record_tenant_audit_log(
            db,
            org,
            action=OrgAuditAction.MEMBER_ROLE_CHANGED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="member",
            target_user_id=target_user.id,
            before_state={"role": old_role},
            after_state={"role": payload.role},
            request=request,
        )

    if payload.is_active is not None and payload.is_active != target_user.is_active:
        target_user.is_active = payload.is_active
        target_user.updated_at = datetime.now(timezone.utc)
        if payload.is_active is False:
            db.query(LoginSession).filter(
                LoginSession.user_id == target_user.id,
                LoginSession.revoked_at.is_(None),
            ).update({"revoked_at": datetime.now(timezone.utc)})
        record_tenant_audit_log(
            db,
            org,
            action=OrgAuditAction.MEMBER_ACTIVATED if payload.is_active else OrgAuditAction.MEMBER_DEACTIVATED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="member",
            target_user_id=target_user.id,
            before_state={"is_active": not payload.is_active},
            after_state={"is_active": payload.is_active},
            request=request,
        )

    db.commit()

    return MemberUpdateResponse(
        user_id=str(target_user.id),
        role=membership.role,
        is_active=target_user.is_active,
    )


@router.post(
    "/organizations/{org_id}/members/{user_id}/reissue-password",
    response_model=ReissueTempPasswordResponse,
)
def reissue_temp_password(
    org_id: str,
    user_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = db.query(UserOrgMembership).filter(
        UserOrgMembership.user_id == user_id,
        UserOrgMembership.organization_id == org_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_MEMBERSHIP_MESSAGE)

    _require_org_admin(current_user, org_id, db)

    org = db.query(Organization).filter(Organization.id == org_id).first()
    target_user = db.query(User).filter(User.id == user_id).first()
    temp_password = generate_temp_password()
    target_user.password_hash = hash_password(temp_password)
    target_user.must_change_password = True
    target_user.updated_at = datetime.now(timezone.utc)

    db.query(LoginSession).filter(
        LoginSession.user_id == target_user.id,
        LoginSession.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc)})

    record_tenant_audit_log(
        db,
        org,
        action=OrgAuditAction.MEMBER_TEMP_PASSWORD_REISSUED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="member",
        target_user_id=target_user.id,
        before_state=None,
        after_state={"email": target_user.email},
        request=request,
    )

    db.commit()

    return ReissueTempPasswordResponse(
        user_id=str(target_user.id),
        temp_password=temp_password,
    )

def _build_verification_token(db: Session, email: str, request_ip: str | None) -> str:
    """Create a single-use email verification token and return the raw token."""
    raw_token = pysecrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    verification_token = EmailVerificationToken(
        id=uuid.uuid4(),
        email=email,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(
            minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
        ),
        request_ip=request_ip,
        created_at=datetime.now(timezone.utc),
    )
    db.add(verification_token)
    db.commit()
    return raw_token


@router.post("/pre-register", response_model=MessageResponse)
@limiter.limit(f"{settings.AUTH_RATE_LIMIT_PER_MINUTE}/minute")
async def pre_register(
    request: Request,
    payload: PreRegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    \u4eee\u767b\u9332\u3002\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306e\u5230\u9054\u6027\u3092\u78ba\u8a8d\u3059\u308b\u305f\u3081\u3001\u78ba\u8a8d\u30e1\u30fc\u30eb\u3092\u9001\u4fe1\u3059\u308b\u3002
    \u65e2\u5b58\u30e6\u30fc\u30b6\u30fc\u306e\u6709\u7121\u306b\u95a2\u308f\u3089\u305a\u540c\u3058\u6c4e\u7528\u30e1\u30c3\u30bb\u30fc\u30b8\u3092\u8fd4\u3059(user enumeration\u5bfe\u7b56)\u3002
    """
    generic_message = MessageResponse(
        message="\u78ba\u8a8d\u30e1\u30fc\u30eb\u3092\u9001\u4fe1\u3057\u307e\u3057\u305f\u3002\u30e1\u30fc\u30eb\u5185\u306e\u30ea\u30f3\u30af\u304b\u3089\u3054\u767b\u9332\u3092\u7d9a\u3051\u3066\u304f\u3060\u3055\u3044\u3002"
    )

    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        # \u65e2\u5b58\u30e6\u30fc\u30b6\u30fc\u306b\u306f\u78ba\u8a8d\u30e1\u30fc\u30eb\u3092\u9001\u3089\u305a\u3001\u901a\u5e38\u306e\u6848\u5185\u306f\u7701\u304f(enumeration\u5bfe\u7b56\u306e\u305f\u3081
        # \u30ec\u30b9\u30dd\u30f3\u30b9\u81ea\u4f53\u306f\u540c\u3058\u6c4e\u7528\u30e1\u30c3\u30bb\u30fc\u30b8\u3092\u8fd4\u3059)
        return generic_message

    client_ip = get_client_ip(request)
    raw_token = _build_verification_token(db, payload.email, client_ip)
    verify_url = f"{settings.FRONTEND_URL}/register/verify?token={raw_token}"

    background_tasks.add_task(send_verification_email, payload.email, verify_url)

    return generic_message


@router.get("/verify-email", response_model=VerifyEmailResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    """
    \u4eee\u767b\u9332\u30e1\u30fc\u30eb\u5185\u30ea\u30f3\u30af\u306e\u30c8\u30fc\u30af\u30f3\u691c\u8a3c\u3002
    \u6709\u52b9\u306a\u3089\u672c\u767b\u9332\u753b\u9762\u3078\u6e21\u3059\u305f\u3081email\u3092\u8fd4\u3059(\u30c8\u30fc\u30af\u30f3\u81ea\u4f53\u306f\u3053\u3053\u3067\u6d88\u8cbb\u3057\u306a\u3044\u3002
    \u672c\u767b\u9332\u5b8c\u4e86\u6642\u306b consumed_at \u3092\u8a18\u9332\u3059\u308b)\u3002
    """
    verification_token = _get_valid_verification_token(db, token)

    if not verification_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u30ea\u30f3\u30af\u304c\u7121\u52b9\u304b\u3001\u6709\u52b9\u671f\u9650\u304c\u5207\u308c\u3066\u3044\u307e\u3059",
        )

    return VerifyEmailResponse(email=verification_token.email)
