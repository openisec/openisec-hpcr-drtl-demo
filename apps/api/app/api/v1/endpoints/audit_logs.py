import csv
import io
import json
from datetime import date as date_type, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_org_db, get_current_user, get_current_session_and_user
from app.core.audit import OrgAuditAction, AuthAuditAction
from app.models.public_models import User, UserOrgMembership, AuthAuditLog, Organization
from app.models.org_models import AuditLog
from app.schemas.audit import (
    AuditLogOut, PaginatedAuditLogResponse,
    AuthAuditLogOut, PaginatedAuthAuditLogResponse,
    AuditActionListResponse,
)

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

ALLOWED_LIMITS = {20, 50, 100}
# CSV出力は page/limit を無視して全件対象にするが、無制限だと事故のもとに
# なるため、安全弁として上限を設ける。超過した場合は上限まで(occurred_at
# 降順)で打ち切り、レスポンスヘッダーで通知する。
CSV_EXPORT_MAX_ROWS = 10000

_NOT_AUTHORIZED_MESSAGE = "この操作を行う権限がありません"


def _validate_limit(limit: int) -> int:
    if limit not in ALLOWED_LIMITS:
        raise HTTPException(status_code=400, detail=f"limit must be one of {sorted(ALLOWED_LIMITS)}")
    return limit


def _parse_date(value: Optional[str], field_name: str) -> Optional[date_type]:
    if value is None:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an ISO date (YYYY-MM-DD)")


def _require_org_admin_role(current_user: User, org_id, db: Session) -> None:
    if current_user.is_platform_admin:
        return
    membership = db.query(UserOrgMembership).filter(
        UserOrgMembership.user_id == current_user.id,
        UserOrgMembership.organization_id == org_id,
        UserOrgMembership.role == "admin",
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail=_NOT_AUTHORIZED_MESSAGE)


def _admin_org_ids(current_user: User, db: Session) -> list[str]:
    """current_user がorg管理者(role='admin')として所属する組織IDの一覧。"""
    rows = db.query(UserOrgMembership.organization_id).filter(
        UserOrgMembership.user_id == current_user.id,
        UserOrgMembership.role == "admin",
    ).all()
    return [str(r[0]) for r in rows]


# ---------------------------------------------------------------------------
# 組織アクティビティ (org_<uuid>.audit_logs)
# ---------------------------------------------------------------------------

def _apply_org_log_filters(query, *, action, actor_email, target_user_id, from_date, to_date):
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_email:
        query = query.filter(AuditLog.actor_email.ilike(f"%{actor_email}%"))
    if target_user_id:
        query = query.filter(AuditLog.target_user_id == target_user_id)
    if from_date:
        query = query.filter(AuditLog.occurred_at >= from_date)
    if to_date:
        query = query.filter(AuditLog.occurred_at < to_date + timedelta(days=1))
    return query


def _resolve_user_emails(db: Session, user_ids: set) -> dict:
    """user_id(str) -> email の対応表。対象ユーザーIDから表示用メールを引くために使う。"""
    user_ids = {uid for uid in user_ids if uid}
    if not user_ids:
        return {}
    rows = db.query(User.id, User.email).filter(User.id.in_(user_ids)).all()
    return {str(uid): email for uid, email in rows}


def _org_log_to_out(log: AuditLog, email_map: dict) -> AuditLogOut:
    target_id = str(log.target_user_id) if log.target_user_id else None
    return AuditLogOut(
        id=str(log.id),
        action=log.action,
        actor_id=str(log.actor_id) if log.actor_id else None,
        actor_email=log.actor_email,
        actor_type=log.actor_type,
        resource_type=log.resource_type,
        resource_id=str(log.resource_id) if log.resource_id else None,
        target_user_id=target_id,
        target_user_email=email_map.get(target_id),
        before_state=log.before_state,
        after_state=log.after_state,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        occurred_at=log.occurred_at,
    )


@router.get("/org", response_model=PaginatedAuditLogResponse)
def list_org_audit_logs(
    ctx=Depends(get_org_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20),
    action: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    target_user_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-08-01"),
    to_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-08-31"),
):
    db, current_user, org = ctx
    _require_org_admin_role(current_user, org.id, db)

    limit = _validate_limit(limit)
    from_date_parsed = _parse_date(from_date, "from_date")
    to_date_parsed = _parse_date(to_date, "to_date")

    base_query = _apply_org_log_filters(
        db.query(AuditLog),
        action=action, actor_email=actor_email, target_user_id=target_user_id,
        from_date=from_date_parsed, to_date=to_date_parsed,
    )

    total = base_query.count()
    logs = base_query.order_by(AuditLog.occurred_at.desc()) \
        .offset((page - 1) * limit).limit(limit).all()

    email_map = _resolve_user_emails(db, {str(l.target_user_id) for l in logs if l.target_user_id})

    return PaginatedAuditLogResponse(
        items=[_org_log_to_out(l, email_map) for l in logs], total=total, page=page, limit=limit,
    )


@router.get("/org/export")
def export_org_audit_logs(
    ctx=Depends(get_org_db),
    action: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    target_user_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    db, current_user, org = ctx
    _require_org_admin_role(current_user, org.id, db)

    from_date_parsed = _parse_date(from_date, "from_date")
    to_date_parsed = _parse_date(to_date, "to_date")

    base_query = _apply_org_log_filters(
        db.query(AuditLog),
        action=action, actor_email=actor_email, target_user_id=target_user_id,
        from_date=from_date_parsed, to_date=to_date_parsed,
    )
    logs = base_query.order_by(AuditLog.occurred_at.desc()).limit(CSV_EXPORT_MAX_ROWS).all()
    email_map = _resolve_user_emails(db, {str(l.target_user_id) for l in logs if l.target_user_id})

    # 先にCSV本文を組み立てる。record_tenant_audit_log側のcommit()は
    # セッション内の既存インスタンス(logs)を失効(expire)させ、コミット後は
    # SET LOCAL search_path もリセットされるため、commit後にlogsへ再アクセス
    # すると対象スキーマが見えずObjectDeletedErrorになる。
    # そのため監査ログ記録・commitは最後に行う。
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "occurred_at", "action", "actor_email", "actor_type", "resource_type",
        "resource_id", "target_user_id", "target_user_email", "ip_address", "user_agent",
        "before_state", "after_state",
    ])
    for l in logs:
        target_id = str(l.target_user_id) if l.target_user_id else ""
        writer.writerow([
            l.occurred_at.isoformat(), l.action, l.actor_email or "", l.actor_type,
            l.resource_type or "", l.resource_id or "", target_id, email_map.get(target_id, ""),
            l.ip_address or "", l.user_agent or "",
            json.dumps(l.before_state, ensure_ascii=False) if l.before_state else "",
            json.dumps(l.after_state, ensure_ascii=False) if l.after_state else "",
        ])
    row_count = len(logs)

    from app.core.audit import record_tenant_audit_log
    record_tenant_audit_log(
        db, org,
        action=OrgAuditAction.AUDIT_LOG_EXPORTED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="audit_log",
        before_state=None,
        after_state={"format": "csv", "row_count": row_count},
    )
    db.commit()

    headers = {"Content-Disposition": "attachment; filename=audit_logs.csv"}
    if len(logs) >= CSV_EXPORT_MAX_ROWS:
        headers["X-Export-Truncated"] = "true"
    return Response(content=buf.getvalue(), media_type="text/csv", headers=headers)


@router.get("/org/actions", response_model=AuditActionListResponse)
def list_org_audit_actions(ctx=Depends(get_org_db)):
    db, current_user, org = ctx
    _require_org_admin_role(current_user, org.id, db)
    actions = [
        v for k, v in vars(OrgAuditAction).items()
        if not k.startswith("_") and isinstance(v, str)
    ]
    return AuditActionListResponse(actions=sorted(actions))


# ---------------------------------------------------------------------------
# 認証ログ (public.auth_audit_logs)
# ---------------------------------------------------------------------------

def _apply_auth_log_filters(query, *, action, actor_email, from_date, to_date):
    if action:
        query = query.filter(AuthAuditLog.action == action)
    if actor_email:
        query = query.filter(AuthAuditLog.actor_email.ilike(f"%{actor_email}%"))
    if from_date:
        query = query.filter(AuthAuditLog.occurred_at >= from_date)
    if to_date:
        query = query.filter(AuthAuditLog.occurred_at < to_date + timedelta(days=1))
    return query


def _resolve_org_names(db: Session, org_ids: set) -> dict:
    org_ids = {oid for oid in org_ids if oid}
    if not org_ids:
        return {}
    rows = db.query(Organization.id, Organization.name).filter(Organization.id.in_(org_ids)).all()
    return {str(oid): name for oid, name in rows}


def _auth_log_to_out(log: AuthAuditLog, org_name_map: dict) -> AuthAuditLogOut:
    org_id = str(log.org_id) if log.org_id else None
    return AuthAuditLogOut(
        id=str(log.id),
        action=log.action,
        actor_id=str(log.actor_id) if log.actor_id else None,
        actor_email=log.actor_email,
        org_id=org_id,
        org_name=org_name_map.get(org_id),
        target_user_id=str(log.target_user_id) if log.target_user_id else None,
        detail=log.detail,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        occurred_at=log.occurred_at,
    )


def _scope_auth_query_to_accessible_orgs(
    query, current_user: User, org_id: Optional[str], db: Session, active_org_id: Optional[str] = None,
):
    """
    platform_admin: org_id指定があればそれで絞り込み、無指定なら全件。
    org管理者: org_id指定があればそれ(adminロールを持つ組織の範囲内)で絞り込み、
    無指定の場合は「現在アクティブな組織」(画面上部で切り替えた組織)をデフォルトに
    する。複数組織のadminを兼務している場合でも、無指定時に全組織分が混在して
    表示されると「今見ている組織」が分かりにくくなるため、まず現在の組織に絞る。
    他の管理組織を見たい場合はorg_idを明示的に指定する。
    admin権限を持つ組織が一つもなければ403。
    """
    if current_user.is_platform_admin:
        if org_id:
            query = query.filter(AuthAuditLog.org_id == org_id)
        return query

    admin_org_ids = _admin_org_ids(current_user, db)
    if not admin_org_ids:
        raise HTTPException(status_code=403, detail=_NOT_AUTHORIZED_MESSAGE)

    target_org_id = org_id or (active_org_id if active_org_id in admin_org_ids else None)
    if org_id and org_id not in admin_org_ids:
        raise HTTPException(status_code=403, detail=_NOT_AUTHORIZED_MESSAGE)

    if target_org_id:
        query = query.filter(AuthAuditLog.org_id == target_org_id)
    else:
        # 現在の組織でadmin権限を持っていない(他組織のみadmin)場合は、
        # 従来通りadminを持つ全組織で絞り込む。
        query = query.filter(AuthAuditLog.org_id.in_(admin_org_ids))
    return query


@router.get("/auth", response_model=PaginatedAuthAuditLogResponse)
def list_auth_audit_logs(
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20),
    action: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    org_id: Optional[str] = Query(None, description="platform_admin/複数組織admin向けの絞り込み。org管理者は無指定時、現在アクティブな組織がデフォルト"),
    from_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-08-01"),
    to_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-08-31"),
):
    login_session, current_user = session_and_user
    active_org_id = str(login_session.active_org_id or current_user.organization_id)

    limit = _validate_limit(limit)
    from_date_parsed = _parse_date(from_date, "from_date")
    to_date_parsed = _parse_date(to_date, "to_date")

    base_query = _scope_auth_query_to_accessible_orgs(
        db.query(AuthAuditLog), current_user, org_id, db, active_org_id=active_org_id,
    )
    base_query = _apply_auth_log_filters(
        base_query, action=action, actor_email=actor_email,
        from_date=from_date_parsed, to_date=to_date_parsed,
    )

    total = base_query.count()
    logs = base_query.order_by(AuthAuditLog.occurred_at.desc()) \
        .offset((page - 1) * limit).limit(limit).all()

    org_name_map = _resolve_org_names(db, {str(l.org_id) for l in logs if l.org_id})

    return PaginatedAuthAuditLogResponse(
        items=[_auth_log_to_out(l, org_name_map) for l in logs], total=total, page=page, limit=limit,
    )


@router.get("/auth/export")
def export_auth_audit_logs(
    session_and_user: tuple = Depends(get_current_session_and_user),
    db: Session = Depends(get_db),
    action: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    org_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    login_session, current_user = session_and_user
    active_org_id = str(login_session.active_org_id or current_user.organization_id)

    from_date_parsed = _parse_date(from_date, "from_date")
    to_date_parsed = _parse_date(to_date, "to_date")

    base_query = _scope_auth_query_to_accessible_orgs(
        db.query(AuthAuditLog), current_user, org_id, db, active_org_id=active_org_id,
    )
    base_query = _apply_auth_log_filters(
        base_query, action=action, actor_email=actor_email,
        from_date=from_date_parsed, to_date=to_date_parsed,
    )
    logs = base_query.order_by(AuthAuditLog.occurred_at.desc()).limit(CSV_EXPORT_MAX_ROWS).all()
    org_name_map = _resolve_org_names(db, {str(l.org_id) for l in logs if l.org_id})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "occurred_at", "action", "actor_email", "org_id", "org_name", "target_user_id",
        "ip_address", "user_agent", "detail",
    ])
    for l in logs:
        org_id = str(l.org_id) if l.org_id else ""
        writer.writerow([
            l.occurred_at.isoformat(), l.action, l.actor_email or "",
            org_id, org_name_map.get(org_id, ""), l.target_user_id or "",
            l.ip_address or "", l.user_agent or "",
            json.dumps(l.detail, ensure_ascii=False) if l.detail else "",
        ])

    headers = {"Content-Disposition": "attachment; filename=auth_audit_logs.csv"}
    if len(logs) >= CSV_EXPORT_MAX_ROWS:
        headers["X-Export-Truncated"] = "true"
    return Response(content=buf.getvalue(), media_type="text/csv", headers=headers)


@router.get("/auth/actions", response_model=AuditActionListResponse)
def list_auth_audit_actions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_platform_admin and not _admin_org_ids(current_user, db):
        raise HTTPException(status_code=403, detail=_NOT_AUTHORIZED_MESSAGE)
    actions = [
        v for k, v in vars(AuthAuditAction).items()
        if not k.startswith("_") and isinstance(v, str)
    ]
    return AuditActionListResponse(actions=sorted(actions))
