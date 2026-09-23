"""
監査ログ記録ヘルパー。

2つの記録先を使い分ける:
  - record_auth_audit_log(): public.auth_audit_logs
    ログイン成功/失敗、ログアウト、パスワード変更、メール確認、組織切り替え、
    メンバー管理など、特定の組織のテナントスキーマに一意に紐づかない、または
    組織所属確定前に発生しうるイベント。
  - record_audit_log(): org_<uuid>.audit_logs (org_models.AuditLog)
    セッションの完了/終了、承認/却下、リスクスコア閾値変更等、組織スコープの
    操作。get_org_db 経由で既にテナントスキーマの search_path が設定された
    db セッションを渡すこと。

いずれも db.add() のみ行い、db.commit() は呼ばない。呼び出し元の
トランザクションに便乗させることで、「本処理は成功したが監査ログだけ
記録漏れした」という不整合を防ぐ。
"""
import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.public_models import AuthAuditLog
from app.models.org_models import AuditLog


class AuthAuditAction:
    LOGIN_SUCCESS = "auth.login_success"
    LOGIN_FAILURE = "auth.login_failure"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password_changed"
    EMAIL_VERIFIED = "auth.email_verified"
    ORG_SWITCHED = "authz.org_switched"
    SWITCH_OUT = "auth.switch_out"
    SWITCH_IN_SUCCESS = "auth.switch_in_success"
    SWITCH_IN_FAILURE = "auth.switch_in_failure"
    MEMBER_ADDED = "authz.member_added"
    MEMBER_REMOVED = "authz.member_removed"
    ROLE_CHANGED = "authz.role_changed"
    PLATFORM_ADMIN_CHANGED = "authz.platform_admin_changed"


class OrgAuditAction:
    SESSION_COMPLETED = "session.completed"
    SESSION_CLOSED = "session.closed"
    SESSION_APPROVED = "session.approved"
    SESSION_REJECTED = "session.rejected"
    SESSION_DELETED = "session.deleted"
    RISK_THRESHOLD_CHANGED = "org.risk_threshold_changed"
    MEMBER_CREATED = "member.created"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_ACTIVATED = "member.activated"
    MEMBER_DEACTIVATED = "member.deactivated"
    MEMBER_ORG_MOVED = "member.org_moved"
    MEMBER_TEMP_PASSWORD_REISSUED = "member.temp_password_reissued"
    AUDIT_LOG_VIEWED = "audit.viewed"
    AUDIT_LOG_EXPORTED = "audit.exported"


def build_message_snapshot(db: Session, msg, session_title: str, session_status: str) -> dict:
    """
    セッション詳細ページに実際に表示される内容一式を、監査ログの
    before_state/after_state用にJSON化可能な辞書として組み立てる。

    Completed/Closed/削除のいずれのイベントも、この同一関数を通す
    ことで「その時点の詳細ページ表示内容」という一貫した形式に
    揃える(個別にフィールドを選別しない)。

    循環importを避けるため、endpoints.sessions._to_message_out とは
    独立してここで組み立てる(ロジックは同等)。
    """
    from app.models.org_models import Approval
    from app.models.public_models import User

    approval = (
        db.query(Approval)
        .filter(Approval.message_id == msg.id)
        .order_by(Approval.decided_at.desc().nullslast())
        .first()
    )
    approval_status = None
    approval_comment = None
    approved_by_name = None
    approved_by_email = None
    approved_at = None
    if approval and approval.status in ("approved", "rejected"):
        approval_status = approval.status
        approval_comment = approval.comment
        approver = db.query(User).filter(User.id == approval.approver_id).first()
        approved_by_name = approver.full_name if approver else None
        approved_by_email = approver.email if approver else None
        if approval.status == "approved":
            approved_at = approval.decided_at.isoformat() if approval.decided_at else None

    return {
        "title": session_title,
        "status": session_status,
        "query": msg.query,
        "history": msg.history,
        "pro": msg.pro or [],
        "con": msg.con or [],
        "recommendation": msg.recommendation,
        "decision_type": msg.decision_type,
        "risk_score": msg.risk_score,
        "risk_category": msg.risk_category or [],
        "response_confidence_score": msg.response_confidence_score,
        "response_confidence_level": msg.response_confidence_level,
        "decision": msg.decision,
        "reason": msg.reason,
        "ai_recommendation_action": msg.ai_recommendation_action,
        "target_date": msg.target_date.isoformat() if msg.target_date else None,
        "decided_at": msg.decided_at.isoformat() if msg.decided_at else None,
        "approval_status": approval_status,
        "approval_comment": approval_comment,
        "approved_by_name": approved_by_name,
        "approved_by_email": approved_by_email,
        "approved_at": approved_at,
        "addendum": msg.addendum,
        "addendum_updated_at": msg.addendum_updated_at.isoformat() if msg.addendum_updated_at else None,
    }


def record_tenant_audit_log(
    db: Session,
    org,
    action: str,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    request: Request | None = None,
) -> None:
    """
    public スキーマのDBセッション(get_db)から、org_<uuid> テナント
    スキーマの audit_logs に書き込むためのヘルパー。同一トランザクション
    内で一時的に search_path を切り替える(SET LOCALはトランザクション
    終了時に自動的に元へ戻る)。org は public_models.Organization インス
    タンス(pg_schema属性を持つもの)を渡す。

    重要: db.add() は実際のINSERTを commit/flush まで遅延させるため、
    この関数を複数回(異なるorgに対して)連続で呼ぶ場合、後続の呼び出しで
    search_path を切り替えてから初めてflushされると、前の呼び出し分の
    ログが誤って新しいsearch_path側のスキーマに書き込まれてしまう。
    これを防ぐため、SET LOCAL 実行後・次の切り替えが起きる前に必ず
    flush して、現在のsearch_pathのうちにINSERTを確定させる。
    """
    from sqlalchemy import text
    db.execute(text('SET LOCAL search_path TO "%s", public' % org.pg_schema))
    record_audit_log(
        db,
        org_id=org.id,
        action=action,
        actor_id=actor_id,
        actor_email=actor_email,
        resource_type=resource_type,
        resource_id=resource_id,
        target_user_id=target_user_id,
        before_state=before_state,
        after_state=after_state,
        request=request,
    )
    db.flush()


def get_client_ip(request: Request) -> str | None:
    """
    クライアントの実IPアドレスを取得する。

    Cloud Run環境ではリクエストがGoogleのフロントエンドプロキシを経由する
    ため、request.client.host はプロキシ側のIPになる可能性がある。
    X-Forwarded-For ヘッダーが付与されていればその先頭値(最初にプロキシへ
    到達したクライアントのIP)を優先し、無ければ request.client.host に
    フォールバックする。

    注意: この実装はdev環境での動作確認がまだ済んでいない。Cloud Run上で
    X-Forwarded-For の値が信頼できる形で渡ってくるか要検証。
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


def get_client_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")[:500]


def record_auth_audit_log(
    db: Session,
    action: str,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    org_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    detail: dict | None = None,
    request: Request | None = None,
) -> None:
    log = AuthAuditLog(
        id=uuid.uuid4(),
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        org_id=org_id,
        target_user_id=target_user_id,
        detail=detail,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_client_user_agent(request) if request else None,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(log)


def record_audit_log(
    db: Session,
    org_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    request: Request | None = None,
) -> None:
    log = AuditLog(
        id=uuid.uuid4(),
        org_id=org_id,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_type="human",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        target_user_id=target_user_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_client_user_agent(request) if request else None,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(log)
