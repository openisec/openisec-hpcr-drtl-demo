import json
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_org_db
from app.core.security import validate_input, mask_pii
from app.core.audit import record_audit_log, build_message_snapshot, OrgAuditAction
from app.models.org_models import Session as OrgSession, Message, AuditLog, Approval
from app.models.public_models import User, UserOrgMembership
from app.services.gemini_service import analyze_with_gemini
from app.services.model_armor_service import check_prompt_injection, PromptBlockedError
from app.services.mail_service import send_risk_alert_email, send_approval_request_email, send_rejection_email

router = APIRouter()
settings = get_settings()


def _get_approver_emails(db: Session, org_id) -> list[str]:
    """
    G. 組織内で role=="approver" のアクティブなメンバー全員のメール
    アドレスを返す。User/UserOrgMembership は public スキーマ明示指定
    のため、テナントスキーマへの search_path 中でも安全に参照できる。
    """
    rows = (
        db.query(User.email)
        .join(UserOrgMembership, UserOrgMembership.user_id == User.id)
        .filter(
            UserOrgMembership.organization_id == org_id,
            UserOrgMembership.role == "approver",
            User.is_active == True,
        )
        .all()
    )
    return [r[0] for r in rows]


def _session_url(session_id) -> str:
    return f"{settings.FRONTEND_URL}/dashboard/{session_id}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class MessageRequest(BaseModel):
    query: str
    history_context: Optional[str] = None
    decision_type: Optional[str] = None


AI_RECOMMENDATION_ACTIONS = {"adopted", "modified", "rejected"}


class DecisionRequest(BaseModel):
    decision: str
    ai_recommendation_action: str
    reason: str
    target_date: str  # ISO format: YYYY-MM-DD

    @field_validator("ai_recommendation_action")
    @classmethod
    def validate_ai_recommendation_action(cls, v: str) -> str:
        if v not in AI_RECOMMENDATION_ACTIONS:
            raise ValueError(
                f"ai_recommendation_action must be one of {sorted(AI_RECOMMENDATION_ACTIONS)}"
            )
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v


class DraftDecisionUpdate(BaseModel):
    """Autosave for in-progress decision/ai_recommendation_action/reason/target_date, before Log is pressed."""
    decision: Optional[str] = None
    ai_recommendation_action: Optional[str] = None
    reason: Optional[str] = None
    target_date: Optional[str] = None  # ISO format: YYYY-MM-DD

    @field_validator("ai_recommendation_action")
    @classmethod
    def validate_ai_recommendation_action(cls, v: Optional[str]) -> Optional[str]:
        # 自動保存(フロントの未選択状態)は空文字で送られてくるため、Noneとして扱う
        if not v:
            return None
        if v not in AI_RECOMMENDATION_ACTIONS:
            raise ValueError(
                f"ai_recommendation_action must be one of {sorted(AI_RECOMMENDATION_ACTIONS)}"
            )
        return v


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
    background_tasks: BackgroundTasks,
    org_db=Depends(get_org_db),
):
    db, current_user, org = org_db

    # Validate session (A案: 分析は1セッションにつき1回のみ。draft状態でのみ許可)
    session = db.query(OrgSession).filter(
        OrgSession.id == session_id,
        OrgSession.created_by == current_user.id,
        OrgSession.status == "draft",
    ).first()
    if not session:
        raise HTTPException(
            status_code=409,
            detail="このセッションは既に分析済みか、存在しないため再分析できません。",
        )

    # Input Guardrail (LLM01/LLM04): regex-based check
    is_valid, reason = validate_input(payload.query)
    if not is_valid:
        raise HTTPException(status_code=422, detail=f"Input validation failed: {reason}")

    # Input Guardrail (LLM01): Model Armor ML-based prompt injection /
    # jailbreak detection, as a second layer on top of the regex check above.
    try:
        await check_prompt_injection(payload.query)
    except PromptBlockedError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # PII masking before sending to AI (LLM02)
    safe_query = mask_pii(payload.query)
    safe_history = mask_pii(payload.history_context) if payload.history_context else None

    # 注意: Gemini呼び出しは、DBへの書き込み(add/commit)より前に行う。
    # tenant_schema() の SET LOCAL search_path はトランザクション境界で
    # リセットされるため、途中でcommitを挟むと、後続のUPDATE/INSERTが
    # 誤って public スキーマに対して実行されてしまう(実害: 分析結果が
    # 実際には保存されない)。また、Gemini呼び出し失敗時にプレース
    # ホルダー行だけ削除してもセッションのstatusが"open"のまま残り、
    # 再分析できなくなる不具合もあったため、DB書き込みは分析成功後の
    # 一度きりのcommitにまとめる。
    try:
        # Call Gemini Flash (LLM05: output validated in service)
        hpcr_drtl = await analyze_with_gemini(
            query=safe_query,
            history_context=safe_history,
            decision_type=payload.decision_type,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)[:200]}")

    confidence = hpcr_drtl.get("response_confidence", {})
    log_summary = (
        f"Query analyzed. Risk: {hpcr_drtl.get('risk_score', 0)}/100. "
        f"Confidence: {confidence.get('level', 'unknown')}. "
        f"Auto-generated at {datetime.now(timezone.utc).isoformat()}"
    )[:500]

    msg = Message(
        id=uuid.uuid4(),
        session_id=session.id,
        query=payload.query,
        history=hpcr_drtl.get("history", ""),
        pro=hpcr_drtl.get("pro", []),
        con=hpcr_drtl.get("con", []),
        recommendation=hpcr_drtl.get("recommendation", ""),
        risk_score=hpcr_drtl.get("risk_score", 0),
        risk_category=hpcr_drtl.get("risk_category", []),
        response_confidence_score=confidence.get("score", 0),
        response_confidence_level=confidence.get("level", "low"),
        response_confidence_limiting_factors=confidence.get("limiting_factors", []),
        log=log_summary,
        actor_type="Human",
        decision_type=payload.decision_type,
    )
    session.status = "open"
    db.add(session)
    db.add(msg)
    # flush() はトランザクションを終了させない(search_path はまだ有効)ため、
    # ここで TimestampMixin の Python 側デフォルト(created_at)を確定させ、
    # commit 前に応答用の値を全てスナップショットしておく。
    db.flush()
    msg_id = msg.id
    created_at_snapshot = msg.created_at.isoformat() if msg.created_at else None
    history_snapshot = msg.history
    pro_snapshot = msg.pro
    con_snapshot = msg.con
    recommendation_snapshot = msg.recommendation
    risk_score_snapshot = msg.risk_score
    risk_category_snapshot = msg.risk_category
    confidence_score_snapshot = msg.response_confidence_score
    confidence_level_snapshot = msg.response_confidence_level
    confidence_factors_snapshot = msg.response_confidence_limiting_factors
    log_snapshot = msg.log
    session_title_snapshot = session.title

    # G. リスクスコアが組織の閾値以上と判明した時点で、承認者へ内容確認
    # メールを送る(この時点ではまだ承認不要。ステータスはopenのまま)。
    # メール送信対象(approver一覧)は commit 前、search_path が有効な
    # うちに確定させ、BackgroundTasks には文字列のリストのみを渡す
    # (get_org_db の db セッションを BackgroundTasks 内で再利用しない)。
    approver_emails: list[str] = []
    if risk_score_snapshot >= org.risk_score_threshold:
        approver_emails = _get_approver_emails(db, org.id)

    db.commit()

    for email in approver_emails:
        background_tasks.add_task(
            send_risk_alert_email,
            email,
            session_title_snapshot,
            risk_score_snapshot,
            _session_url(session_id),
        )

    return {
        "id": str(msg_id),
        "query": payload.query,
        "session_id": str(session_id),
        "history": history_snapshot,
        "pro": pro_snapshot,
        "con": con_snapshot,
        "recommendation": recommendation_snapshot,
        "decision": None,
        "risk_score": risk_score_snapshot,
        "risk_category": risk_category_snapshot,
        "response_confidence_score": confidence_score_snapshot,
        "response_confidence_level": confidence_level_snapshot,
        "response_confidence_limiting_factors": confidence_factors_snapshot,
        "log": log_snapshot,
        "status": "awaiting_decision",
        "created_at": created_at_snapshot,
    }


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/messages/{message_id}/decision
# ---------------------------------------------------------------------------
@router.post("/sessions/{session_id}/messages/{message_id}/decision", status_code=200)
def record_decision(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: DecisionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    org_db=Depends(get_org_db),
):
    db, current_user, org = org_db

    # F. セッション共有(read-only): 編集は作成者のみ。組織内の他ユーザーは
    # get_session で閲覧はできるが、決定の記録はできない。
    msg = db.query(Message).join(OrgSession).filter(
        Message.id == message_id,
        Message.session_id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.decision = payload.decision[:1000]
    msg.ai_recommendation_action = payload.ai_recommendation_action
    msg.reason = payload.reason[:2000]
    msg.decision_by = current_user.id
    msg.decided_at = datetime.now(timezone.utc)
    msg.target_date = date.fromisoformat(payload.target_date)

    # G. 事前承認ワークフロー: リスクスコアが組織の閾値以上なら、直接
    # completed にはせず、承認者の承認待ち(awaiting_approval)にする。
    sess = db.query(OrgSession).filter(OrgSession.id == session_id).first()
    requires_approval = msg.risk_score >= org.risk_score_threshold
    new_status = "awaiting_approval" if requires_approval else "completed"
    if sess:
        sess.status = new_status

    # commit 前に応答用の値をスナップショット(理由は create_session と同じ:
    # commit 後は search_path が public に戻り、かつ expire_on_commit=True
    # のため属性アクセス・refresh() が失敗する)
    msg_id = msg.id
    decision_snapshot = msg.decision
    ai_recommendation_action_snapshot = msg.ai_recommendation_action
    reason_snapshot = msg.reason
    target_date_snapshot = msg.target_date.isoformat() if msg.target_date else None
    decided_at_snapshot = msg.decided_at.isoformat()
    session_title_snapshot = sess.title if sess else ""
    risk_score_snapshot = msg.risk_score

    approver_emails: list[str] = []
    if requires_approval:
        approver_emails = _get_approver_emails(db, org.id)

    # 監査ログ: 承認不要で即completedになったケースのみここで記録する。
    # 承認が必要なケース(awaiting_approval)は、実際にcompletedへ遷移する
    # approve_message側で記録する。
    if new_status == "completed" and sess:
        record_audit_log(
            db,
            org_id=org.id,
            action=OrgAuditAction.SESSION_COMPLETED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="session",
            resource_id=session_id,
            before_state=None,
            after_state=build_message_snapshot(db, msg, session_title_snapshot, new_status),
            request=request,
        )

    db.commit()

    for email in approver_emails:
        background_tasks.add_task(
            send_approval_request_email,
            email,
            session_title_snapshot,
            risk_score_snapshot,
            _session_url(session_id),
        )

    return {
        "id": str(msg_id),
        "decision": decision_snapshot,
        "ai_recommendation_action": ai_recommendation_action_snapshot,
        "reason": reason_snapshot,
        "target_date": target_date_snapshot,
        "decided_at": decided_at_snapshot,
        "session_status": new_status,
        "requires_approval": requires_approval,
        "message": "Decision recorded successfully",
    }

# ---------------------------------------------------------------------------
# PATCH /sessions/{session_id}/messages/{message_id}/draft-decision
# ---------------------------------------------------------------------------
@router.patch("/sessions/{session_id}/messages/{message_id}/draft-decision", status_code=200)
def update_draft_decision(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: DraftDecisionUpdate,
    org_db=Depends(get_org_db),
):
    """
    入力途中の Decision/Reason/Target を自動保存する(Log 未押下、つまり
    セッションが「進行中(open)」で分析済みだが、まだ決定を確定していない
    状態)。確定済み(decided_at が入っている)メッセージは対象外。
    decision/reason/target_date カラムを Log 時と共用するが、
    decision_by・decided_at は設定しないことで「未確定(進行中)」と区別する。
    """
    db, current_user, _ = org_db

    # F. セッション共有(read-only): 編集は作成者のみに限定する。
    msg = db.query(Message).join(OrgSession).filter(
        Message.id == message_id,
        Message.session_id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg.decided_at is not None:
        raise HTTPException(
            status_code=409,
            detail="既に決定が確定しているため、下書きの自動保存はできません。",
        )

    msg.decision = payload.decision[:1000] if payload.decision else None
    msg.ai_recommendation_action = payload.ai_recommendation_action
    msg.reason = payload.reason[:2000] if payload.reason else None
    msg.target_date = date.fromisoformat(payload.target_date) if payload.target_date else None

    # commit 前に応答用の値をスナップショット
    msg_id = msg.id
    decision_snapshot = msg.decision
    ai_recommendation_action_snapshot = msg.ai_recommendation_action
    reason_snapshot = msg.reason
    target_date_snapshot = msg.target_date.isoformat() if msg.target_date else None

    db.commit()

    return {
        "id": str(msg_id),
        "decision": decision_snapshot,
        "ai_recommendation_action": ai_recommendation_action_snapshot,
        "reason": reason_snapshot,
        "target_date": target_date_snapshot,
    }


# ---------------------------------------------------------------------------
# G. 事前承認ワークフロー: 承認 / 差し戻し / 追記
# ---------------------------------------------------------------------------
class ApprovalDecisionRequest(BaseModel):
    comment: Optional[str] = None


class AddendumUpdate(BaseModel):
    addendum: str

    @field_validator("addendum")
    @classmethod
    def validate_addendum(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("addendum must not be empty")
        return v


def _require_approver(db: Session, current_user: User, org_id) -> None:
    membership = (
        db.query(UserOrgMembership)
        .filter(
            UserOrgMembership.user_id == current_user.id,
            UserOrgMembership.organization_id == org_id,
            UserOrgMembership.role == "approver",
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="承認者のみ実行できます。")


@router.post("/sessions/{session_id}/messages/{message_id}/approve", status_code=200)
def approve_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    request: Request,
    org_db=Depends(get_org_db),
):
    """
    G. 承認者による承認。承認者の内、誰か一人が承認すればそれで完了(completed)
    となる(先着方式)。
    """
    db, current_user, org = org_db
    _require_approver(db, current_user, org.id)

    sess = db.query(OrgSession).filter(OrgSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail="承認待ち状態のセッションのみ承認できます。",
        )

    msg = db.query(Message).filter(
        Message.id == message_id, Message.session_id == session_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    approval = Approval(
        id=uuid.uuid4(),
        session_id=sess.id,
        message_id=msg.id,
        requested_by=sess.created_by,
        approver_id=current_user.id,
        status="approved",
        comment=payload.comment[:1000] if payload.comment else None,
        decided_at=datetime.now(timezone.utc),
    )
    sess.status = "completed"
    db.add(approval)
    db.add(sess)

    approver_name = current_user.full_name

    # build_message_snapshot() 内で Approval を再クエリするため、直前に
    # 追加した approval がpending状態のままだと拾えないことがある。
    # 明示的にflushして、クエリから見える状態にしてから監査ログを組み立てる。
    db.flush()

    record_audit_log(
        db,
        org_id=org.id,
        action=OrgAuditAction.SESSION_COMPLETED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="session",
        resource_id=session_id,
        before_state=None,
        after_state=build_message_snapshot(db, msg, sess.title, "completed"),
        request=request,
    )

    db.commit()

    return {
        "session_status": "completed",
        "approval_status": "approved",
        "approved_by_name": approver_name,
        "message": "承認しました",
    }


@router.post("/sessions/{session_id}/messages/{message_id}/reject", status_code=200)
def reject_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    org_db=Depends(get_org_db),
):
    """
    G. 承認者による差し戻し。セッションは「進行中(open)」に戻り、利用者が
    Decision/Reason/Targetを修正のうえ再度Logできるようにする。
    差し戻し後、作成者(利用者)へ通知メールを送る。
    """
    db, current_user, org = org_db
    _require_approver(db, current_user, org.id)

    sess = db.query(OrgSession).filter(OrgSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail="承認待ち状態のセッションのみ差し戻せます。",
        )

    msg = db.query(Message).filter(
        Message.id == message_id, Message.session_id == session_id
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    approval = Approval(
        id=uuid.uuid4(),
        session_id=sess.id,
        message_id=msg.id,
        requested_by=sess.created_by,
        approver_id=current_user.id,
        status="rejected",
        comment=payload.comment[:1000] if payload.comment else None,
        decided_at=datetime.now(timezone.utc),
    )
    sess.status = "open"
    # 差し戻し: decision/reason/target_dateの値は残し、利用者が修正のうえ
    # 再度Logできるよう、確定情報(decision_by/decided_at)のみクリアする。
    msg.decision_by = None
    msg.decided_at = None
    db.add(approval)
    db.add(sess)
    db.add(msg)

    # commit前にメール送信に必要な値をスナップショット
    creator = db.query(User).filter(User.id == sess.created_by).first()
    creator_email = creator.email if creator else None
    session_title_snapshot = sess.title
    approver_name_snapshot = current_user.full_name
    comment_snapshot = approval.comment

    # build_message_snapshot() 内で Approval を再クエリするため、直前に
    # 追加した approval がpending状態のままだと拾えないことがある。
    db.flush()

    record_audit_log(
        db,
        org_id=org.id,
        action=OrgAuditAction.SESSION_REJECTED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="session",
        resource_id=session_id,
        before_state=None,
        after_state=build_message_snapshot(db, msg, sess.title, "open"),
        request=request,
    )

    db.commit()

    if creator_email:
        background_tasks.add_task(
            send_rejection_email,
            creator_email,
            session_title_snapshot,
            approver_name_snapshot,
            comment_snapshot,
            _session_url(session_id),
        )

    return {
        "session_status": "open",
        "approval_status": "rejected",
        "message": "差し戻しました",
    }


@router.patch("/sessions/{session_id}/messages/{message_id}/addendum", status_code=200)
def update_addendum(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: AddendumUpdate,
    org_db=Depends(get_org_db),
):
    """
    G. 完了(completed)/終了(closed)後の追記。確定フィールド(decision等)は
    編集不可のため、追記専用のこのフィールドのみ作成者が追加できる。
    """
    db, current_user, org = org_db

    msg = db.query(Message).join(OrgSession).filter(
        Message.id == message_id,
        Message.session_id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    sess = db.query(OrgSession).filter(OrgSession.id == session_id).first()
    if not sess or sess.status not in ("completed", "closed"):
        raise HTTPException(
            status_code=409,
            detail="完了・終了状態のセッションにのみ追記できます。",
        )

    msg.addendum = payload.addendum[:2000]
    msg.addendum_updated_at = datetime.now(timezone.utc)

    msg_id = msg.id
    addendum_snapshot = msg.addendum
    addendum_updated_at_snapshot = msg.addendum_updated_at.isoformat()

    db.commit()

    return {
        "id": str(msg_id),
        "addendum": addendum_snapshot,
        "addendum_updated_at": addendum_updated_at_snapshot,
    }
