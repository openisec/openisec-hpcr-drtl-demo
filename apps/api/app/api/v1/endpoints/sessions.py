import uuid
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_org_db
from app.core.audit import record_audit_log, build_message_snapshot, OrgAuditAction
from app.models.public_models import User, UserOrgMembership
from app.models.org_models import Session as OrgSession, Message, DecisionType, Approval
from app.schemas.session import (
    SessionCreate, SessionResponse, MessageOut, DraftQueryUpdate, SharedSessionOut,
    PaginatedSessionResponse, PaginatedSharedSessionOut,
    ApprovalQueueItem, ApprovalQueueResponse, DeleteSessionResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_LIMITS = {20, 50, 100}
# G. 事前承認ワークフロー: open(進行中) -> awaiting_approval(高リスクで承認待ち)
# -> completed(完了)。承認者による差し戻しは awaiting_approval -> open に戻る。
# completed から closed(終了)へは利用者が手動で遷移させる。
ALLOWED_STATUSES = {"draft", "open", "awaiting_approval", "completed", "closed"}


def _latest_approval_for_message(db, message_id) -> Optional[Approval]:
    return (
        db.query(Approval)
        .filter(Approval.message_id == message_id)
        .order_by(Approval.decided_at.desc().nullslast(), Approval.created_at.desc())
        .first()
    )


def _to_message_out(db, msg) -> MessageOut:
    approval = _latest_approval_for_message(db, msg.id)
    approved_by_name = None
    approved_by_email = None
    approval_status = None
    approval_comment = None
    approved_at = None
    if approval and approval.status in ("approved", "rejected"):
        approval_status = approval.status
        approval_comment = approval.comment
        approver = db.query(User).filter(User.id == approval.approver_id).first()
        approved_by_name = approver.full_name if approver else None
        approved_by_email = approver.email if approver else None
        if approval.status == "approved":
            approved_at = approval.decided_at

    return MessageOut(
        id=str(msg.id),
        session_id=str(msg.session_id),
        query=msg.query,
        history=msg.history,
        pro=msg.pro or [],
        con=msg.con or [],
        recommendation=msg.recommendation,
        decision=msg.decision,
        decision_by=str(msg.decision_by) if msg.decision_by else None,
        decided_at=msg.decided_at,
        ai_recommendation_action=msg.ai_recommendation_action,
        reason=msg.reason,
        target_date=msg.target_date,
        log=msg.log,
        risk_score=msg.risk_score,
        risk_category=msg.risk_category or [],
        response_confidence_score=msg.response_confidence_score,
        response_confidence_level=msg.response_confidence_level,
        response_confidence_limiting_factors=msg.response_confidence_limiting_factors or [],
        created_at=msg.created_at,
        approval_status=approval_status,
        approved_by_name=approved_by_name,
        approved_by_email=approved_by_email,
        approval_comment=approval_comment,
        approved_at=approved_at,
        addendum=msg.addendum,
        addendum_updated_at=msg.addendum_updated_at,
    )


def _target_dates_for_sessions(db, session_ids: list) -> dict:
    """ダッシュボード一覧向け: 各セッションのTarget(実施ターゲット日)のみを
    軽量に取得する。A案(1セッション=1メッセージ)前提のため、対象セッションに
    メッセージが複数ある場合は最も新しいものを採用する。"""
    if not session_ids:
        return {}
    rows = (
        db.query(Message.session_id, Message.target_date, Message.created_at)
        .filter(Message.session_id.in_(session_ids))
        .order_by(Message.created_at.asc())
        .all()
    )
    result: dict = {}
    for session_id, target_date, _created_at in rows:
        result[session_id] = target_date
    return result


def _approved_dates_for_sessions(db, session_ids: list) -> dict:
    """ダッシュボード一覧向け: 各セッションの「Approved Date」(最新の承認日時)
    のみを軽量に取得する。承認を受けていないセッションはキーに現れず、
    呼び出し側で .get() の結果がNone(=空欄表示)となる。"""
    if not session_ids:
        return {}
    rows = (
        db.query(Message.session_id, Approval.decided_at)
        .join(Approval, Approval.message_id == Message.id)
        .filter(Message.session_id.in_(session_ids), Approval.status == "approved")
        .order_by(Approval.decided_at.asc())
        .all()
    )
    result: dict = {}
    for session_id, decided_at in rows:
        # 複数回承認された履歴がある場合(差戻し後の再承認等)は最新を採用
        result[session_id] = decided_at
    return result


def _is_approver(db, user_id, org_id) -> bool:
    return (
        db.query(UserOrgMembership)
        .filter(
            UserOrgMembership.user_id == user_id,
            UserOrgMembership.organization_id == org_id,
            UserOrgMembership.role == "approver",
        )
        .first()
        is not None
    )


def _to_session_response(db, session: OrgSession, current_user, org) -> SessionResponse:
    # A案: 1セッション = 1メッセージ想定。念のため作成日時順に並べるが、
    # フロントは先頭(=最新かつ唯一想定)のみを利用する。
    ordered_messages = sorted(session.messages, key=lambda m: m.created_at)
    message_outs = [_to_message_out(db, m) for m in ordered_messages]
    return SessionResponse(
        id=str(session.id),
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        created_by=str(session.created_by),
        draft_query=session.draft_query,
        target_date=ordered_messages[-1].target_date if ordered_messages else None,
        messages=message_outs,
        viewer_is_approver=_is_approver(db, current_user.id, org.id),
        approved_at=message_outs[-1].approved_at if message_outs else None,
    )


def _validate_limit(limit: int) -> int:
    if limit not in ALLOWED_LIMITS:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be one of {sorted(ALLOWED_LIMITS)}",
        )
    return limit


def _validate_status(status: Optional[str]) -> Optional[str]:
    if status is not None and status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(ALLOWED_STATUSES)}",
        )
    return status


def _parse_date(value: Optional[str], field_name: str) -> Optional[date_type]:
    if value is None:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be an ISO date (YYYY-MM-DD)",
        )


def _apply_common_filters(
    query,
    *,
    from_date: Optional[date_type],
    to_date: Optional[date_type],
    status: Optional[str],
    q: Optional[str],
    needs_message_join: bool,
):
    if from_date:
        query = query.filter(OrgSession.created_at >= from_date)
    if to_date:
        # to_date は「その日の終わりまで」を含めるため、日付+1日未満で絞り込む
        query = query.filter(OrgSession.created_at < to_date + timedelta(days=1))
    if status:
        query = query.filter(OrgSession.status == status)
    if q:
        like = f"%{q}%"
        if needs_message_join:
            query = query.outerjoin(Message, Message.session_id == OrgSession.id).filter(
                or_(
                    OrgSession.title.ilike(like),
                    Message.decision.ilike(like),
                    Message.reason.ilike(like),
                )
            ).distinct()
        else:
            query = query.filter(OrgSession.title.ilike(like))
    return query


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
    session_id = session.id
    created_at = session.created_at
    db.add(session)
    db.commit()
    # 注意: db.commit() でトランザクションが終了すると、tenant_schema() が
    # SET LOCAL で設定した search_path がリセットされ public に戻る。
    # さらに SessionLocal は expire_on_commit=True(デフォルト)のため、
    # commit 後は ORM オブジェクトの属性アクセスがすべて DB への
    # 再読み込みを引き起こし、その再読み込みは public スキーマに対して
    # 行われてしまい失敗する(db.refresh() も同様に失敗する)。そのため
    # commit 前に確定している値のみで応答を組み立てる。
    return SessionResponse(
        id=str(session_id),
        title=payload.title,
        status="draft",
        created_at=created_at,
        created_by=str(current_user.id),
        draft_query=None,
        target_date=None,
        messages=[],
        viewer_is_approver=_is_approver(db, current_user.id, org.id),
    )


@router.get("", response_model=PaginatedSessionResponse)
def list_sessions(
    ctx=Depends(get_org_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20),
    from_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-01"),
    to_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-31"),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="タイトル・決定・理由のキーワード検索"),
):
    db, current_user, org = ctx

    limit = _validate_limit(limit)
    status = _validate_status(status)
    from_date_parsed = _parse_date(from_date, "from_date")
    to_date_parsed = _parse_date(to_date, "to_date")

    # ダッシュボード一覧では messages 本文までは不要なため、
    # N+1 を避けるべく messages は含めずに軽量な情報のみ返す。
    base_query = db.query(OrgSession).filter(
        OrgSession.created_by == current_user.id,
    )
    base_query = _apply_common_filters(
        base_query,
        from_date=from_date_parsed,
        to_date=to_date_parsed,
        status=status,
        q=q,
        needs_message_join=True,
    )

    total = base_query.count()
    sessions = base_query.order_by(OrgSession.created_at.desc()) \
        .offset((page - 1) * limit).limit(limit).all()

    # ダッシュボード一覧のTarget列表示用に、フルの messages は読み込まず
    # target_date のみを軽量に取得する(N+1回避のため一括クエリ)。
    target_dates = _target_dates_for_sessions(db, [s.id for s in sessions])
    approved_dates = _approved_dates_for_sessions(db, [s.id for s in sessions])

    items = [
        SessionResponse(
            id=str(s.id),
            title=s.title,
            status=s.status,
            created_at=s.created_at,
            created_by=str(s.created_by),
            target_date=target_dates.get(s.id),
            approved_at=approved_dates.get(s.id),
            messages=[],
        )
        for s in sessions
    ]
    return PaginatedSessionResponse(items=items, total=total, page=page, limit=limit)


@router.get("/shared", response_model=PaginatedSharedSessionOut)
def list_shared_sessions(
    ctx=Depends(get_org_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20),
    from_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-01"),
    to_date: Optional[str] = Query(None, description="ISO date, e.g. 2026-07-31"),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="タイトル・決定・理由のキーワード検索"),
    created_by: Optional[str] = Query(None, description="作成者のユーザーID"),
):
    """
    F. セッション共有(read-only): 組織内の他ユーザーが作成したセッションの一覧。
    テナントスキーマ自体が組織単位で分離されているため、ここでの
    フィルタは「自分以外」であって、組織を跨いだ絞り込みは不要。
    """
    db, current_user, org = ctx

    limit = _validate_limit(limit)
    status = _validate_status(status)
    from_date_parsed = _parse_date(from_date, "from_date")
    to_date_parsed = _parse_date(to_date, "to_date")

    base_query = db.query(OrgSession).filter(
        OrgSession.created_by != current_user.id,
    )
    if created_by:
        base_query = base_query.filter(OrgSession.created_by == created_by)
    base_query = _apply_common_filters(
        base_query,
        from_date=from_date_parsed,
        to_date=to_date_parsed,
        status=status,
        q=q,
        needs_message_join=True,
    )

    total = base_query.count()
    sessions = base_query.order_by(OrgSession.created_at.desc()) \
        .offset((page - 1) * limit).limit(limit).all()

    creator_ids = {s.created_by for s in sessions}
    creators: dict = {}
    if creator_ids:
        rows = db.query(User).filter(User.id.in_(creator_ids)).all()
        creators = {u.id: u for u in rows}

    target_dates = _target_dates_for_sessions(db, [s.id for s in sessions])
    approved_dates = _approved_dates_for_sessions(db, [s.id for s in sessions])

    items = [
        SharedSessionOut(
            id=str(s.id),
            title=s.title,
            status=s.status,
            created_at=s.created_at,
            created_by=str(s.created_by),
            created_by_name=creators[s.created_by].full_name if s.created_by in creators else None,
            created_by_email=creators[s.created_by].email if s.created_by in creators else None,
            target_date=target_dates.get(s.id),
            approved_at=approved_dates.get(s.id),
        )
        for s in sessions
    ]
    return PaginatedSharedSessionOut(items=items, total=total, page=page, limit=limit)


@router.get("/approvals", response_model=ApprovalQueueResponse)
def list_approval_queue(ctx=Depends(get_org_db)):
    """
    G. 承認者向け一覧画面。この組織で「承認が必要になったことがある」
    全セッションを返す(現在承認待ちのものに加え、既に承認/差し戻し
    済みの過去分も含む)。リスクスコア・過去の承認/差し戻し日時(最新)・
    現在のステータスとともに返す。承認者(role=="approver")のみ
    アクセス可能。
    NOTE: ルーティング順序の都合上、この固定パスは /{session_id}(可変パス)
    より前に定義する必要がある。
    """
    db, current_user, org = ctx
    if not _is_approver(db, current_user.id, org.id):
        raise HTTPException(status_code=403, detail="承認者のみアクセスできます。")

    approved_session_ids = db.query(Approval.session_id).distinct().subquery()

    sessions = db.query(OrgSession).options(
        joinedload(OrgSession.messages)
    ).filter(
        or_(
            OrgSession.status == "awaiting_approval",
            OrgSession.id.in_(db.query(approved_session_ids)),
        )
    ).order_by(OrgSession.created_at.desc()).all()

    creator_ids = {s.created_by for s in sessions}
    creators: dict = {}
    if creator_ids:
        rows = db.query(User).filter(User.id.in_(creator_ids)).all()
        creators = {u.id: u for u in rows}

    items = []
    for s in sessions:
        msg = s.messages[0] if s.messages else None
        if not msg:
            continue
        latest_approved = db.query(Approval).filter(
            Approval.message_id == msg.id, Approval.status == "approved"
        ).order_by(Approval.decided_at.desc()).first()
        latest_rejected = db.query(Approval).filter(
            Approval.message_id == msg.id, Approval.status == "rejected"
        ).order_by(Approval.decided_at.desc()).first()

        latest_approved_by_name = None
        if latest_approved:
            approver = db.query(User).filter(User.id == latest_approved.approver_id).first()
            latest_approved_by_name = approver.full_name if approver else None

        items.append(ApprovalQueueItem(
            session_id=str(s.id),
            message_id=str(msg.id),
            title=s.title,
            risk_score=msg.risk_score,
            session_status=s.status,
            created_by_name=creators[s.created_by].full_name if s.created_by in creators else None,
            latest_approved_at=latest_approved.decided_at if latest_approved else None,
            latest_approved_by_name=latest_approved_by_name,
            latest_rejected_at=latest_rejected.decided_at if latest_rejected else None,
        ))

    return ApprovalQueueResponse(items=items)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, ctx=Depends(get_org_db)):
    db, current_user, org = ctx

    # F. セッション共有(read-only): テナントスキーマ自体が組織単位で分離
    # されているため、created_by で絞り込まずに取得することで、組織内の
    # 誰が作成したセッションでも閲覧できる(編集は各エンドポイント側で
    # created_by チェックにより作成者のみに制限)。
    session = db.query(OrgSession).options(
        joinedload(OrgSession.messages)
    ).filter(
        OrgSession.id == session_id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return _to_session_response(db, session, current_user, org)


@router.patch("/{session_id}/draft", response_model=SessionResponse)
def update_draft_query(
    session_id: str,
    payload: DraftQueryUpdate,
    ctx=Depends(get_org_db),
):
    """下書き状態のセッションに対して、入力途中のクエリを自動保存する。"""
    db, current_user, org = ctx

    session = db.query(OrgSession).options(
        joinedload(OrgSession.messages)
    ).filter(
        OrgSession.id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="下書き状態のセッションのみ、入力途中のクエリを保存できます。",
        )

    session.draft_query = payload.draft_query

    # commit 前に、応答に必要な値を全てスナップショットしておく。
    # (create_session と同じ理由: commit 後は search_path が public に
    # 戻った上、expire_on_commit=True によりオブジェクトの属性アクセスが
    # 再読み込みを引き起こし失敗するため)
    session_id = session.id
    title = session.title
    created_at = session.created_at
    created_by = session.created_by
    draft_query = session.draft_query
    ordered_messages = sorted(session.messages, key=lambda m: m.created_at)
    message_snapshots = [_to_message_out(db, m) for m in ordered_messages]

    db.add(session)
    db.commit()

    return SessionResponse(
        id=str(session_id),
        title=title,
        status="draft",
        created_at=created_at,
        created_by=str(created_by),
        draft_query=draft_query,
        target_date=message_snapshots[-1].target_date if message_snapshots else None,
        messages=message_snapshots,
        viewer_is_approver=_is_approver(db, current_user.id, org.id),
    )


class CloseSessionRequest(BaseModel):
    """終了(completed -> closed への遷移)時に、追記(addendum)を同時に保存する
    ためのリクエスト。何らかの対応を実施した結果としての終了操作であるため、
    追記は必須とする。"""

    addendum: str

    @field_validator("addendum")
    @classmethod
    def validate_addendum(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("addendum must not be empty")
        if len(v) > 2000:
            raise ValueError("addendum must be 2000 characters or less")
        return v


@router.post("/{session_id}/close", response_model=SessionResponse)
def close_session(
    session_id: str,
    payload: CloseSessionRequest,
    request: Request,
    ctx=Depends(get_org_db),
):
    """
    G. 完了(completed)状態のセッションを、利用者の手動操作で終了(closed)に
    遷移させる。作成者のみ操作可能。closed以降は通常フィールドの編集は
    一切できず、追記(addendum)のみ可能。

    追記(addendum)は必須。何らかの対応を実施した結果として終了させる操作
    であるため、コメントなしでの終了は許可しない。ステータス変更と同一
    トランザクション内で保存する。以前はこのエンドポイントが追記を一切
    受け取らずに即座に終了状態へ遷移させていたため、「追加コメントを
    入れて終了する」操作でコメントが保存されずステータスのみ終了して
    しまう不具合があった。
    """
    db, current_user, org = ctx

    session = db.query(OrgSession).options(
        joinedload(OrgSession.messages)
    ).filter(
        OrgSession.id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="完了(completed)状態のセッションのみ終了させることができます。",
        )

    session.status = "closed"

    addendum_text = payload.addendum.strip()
    if addendum_text:
        ordered_messages_for_addendum = sorted(session.messages, key=lambda m: m.created_at)
        latest_message = ordered_messages_for_addendum[-1] if ordered_messages_for_addendum else None
        if latest_message:
            latest_message.addendum = addendum_text[:2000]
            latest_message.addendum_updated_at = datetime.now(timezone.utc)
            db.add(latest_message)

    session_id_snap = session.id
    title = session.title
    created_at = session.created_at
    created_by = session.created_by
    draft_query = session.draft_query
    ordered_messages = sorted(session.messages, key=lambda m: m.created_at)
    message_snapshots = [_to_message_out(db, m) for m in ordered_messages]

    if ordered_messages:
        latest_msg = ordered_messages[-1]
        record_audit_log(
            db,
            org_id=org.id,
            action=OrgAuditAction.SESSION_CLOSED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="session",
            resource_id=session.id,
            before_state=None,
            # Closed時点で新たに確定するのは addendum 関連と status のみ。
            # H/P/C/R等の残りは session.completed のログで既に記録済みの
            # ため、ここでは差分のみ記録し、フルスナップショットの重複を
            # 避ける(削除ログは唯一の記録元となるためフルスナップショット
            # のまま据え置き)。
            after_state={
                "title": title,
                "status": "closed",
                "addendum": latest_msg.addendum,
                "addendum_updated_at": latest_msg.addendum_updated_at.isoformat()
                if latest_msg.addendum_updated_at else None,
            },
            request=request,
        )

    db.add(session)
    db.commit()

    return SessionResponse(
        id=str(session_id_snap),
        title=title,
        status="closed",
        created_at=created_at,
        created_by=str(created_by),
        draft_query=draft_query,
        target_date=message_snapshots[-1].target_date if message_snapshots else None,
        messages=message_snapshots,
        viewer_is_approver=_is_approver(db, current_user.id, org.id),
        approved_at=message_snapshots[-1].approved_at if message_snapshots else None,
    )


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
def delete_session(session_id: str, request: Request, ctx=Depends(get_org_db)):
    """
    テストデータの蓄積等でどのログを残すべきか分かりにくくなることを
    避けるため、意思決定ログは基本的に作成者が削除できる。ただし、
    承認を受けたもの(Approval.status == "approved" が存在するもの)は
    削除不可とする。承認済みログの削除は、後続の監査ログ実装により
    「削除しても必要な記録は残る」状態になるまでは許可しない。
    """
    db, current_user, org = ctx

    # joinedload(messages) は使わない: bulk delete(query().delete())と
    # ORMが読み込み済みのコレクションが食い違うと、SQLAlchemyが後続の
    # flushで不整合(0件更新エラー等)を起こすことがあるため、session_id
    # を基準にした直接クエリのみで完結させる。
    session = db.query(OrgSession).filter(
        OrgSession.id == session_id,
        OrgSession.created_by == current_user.id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Approvalはmessage_idだけでなくsession_idも持つため、session_id
    # を基準に判定・削除することで、messages一覧の取得漏れ等に依存せず
    # 確実に判定・削除できるようにする。
    has_approved = db.query(Approval).filter(
        Approval.session_id == session.id,
        Approval.status == "approved",
    ).first() is not None

    if has_approved:
        raise HTTPException(
            status_code=409,
            detail="この意思決定ログは承認済みな為、削除できません。",
        )

    # 削除前に、詳細ページで最終的に表示されていた内容一式を監査ログに
    # 保全する。削除後はセッション・メッセージともにDB上に実体が残らない
    # ため、これが唯一の参照先になる。
    ordered_messages = db.query(Message).filter(
        Message.session_id == session.id
    ).order_by(Message.created_at).all()
    if ordered_messages:
        record_audit_log(
            db,
            org_id=org.id,
            action=OrgAuditAction.SESSION_DELETED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="session",
            resource_id=session.id,
            before_state=build_message_snapshot(db, ordered_messages[-1], session.title, session.status),
            after_state=None,
            request=request,
        )

    db.query(Approval).filter(Approval.session_id == session.id).delete(synchronize_session=False)
    db.query(Message).filter(Message.session_id == session.id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()

    return DeleteSessionResponse()
