from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, date
import uuid

# CTQP: C(きっかけ)/T(事前の考え)の最大文字数(DBカラム長と一致させる)。
CTQP_FIELD_MAX = 1000


class SessionCreate(BaseModel):
    title: str
    decision_type_id: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Title must be 200 characters or less")
        return v.strip()

    @field_validator("decision_type_id")
    @classmethod
    def validate_decision_type_id(cls, v: Optional[str]) -> Optional[str]:
        # UUID列との比較に使うため、UUIDとして不正な値は入口で422にする
        # (検証しないとDB比較で例外になり、500エラーになる)。
        if v is None or v == "":
            return v
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("decision_type_id must be a valid UUID")
        return v


class DraftQueryUpdate(BaseModel):
    """下書き状態のセッションに対する、入力途中クエリの自動保存用スキーマ"""

    draft_query: str
    # CTQP: C(きっかけ)/T(事前の考え)の入力途中内容。未指定(None)の場合は
    # 既存値を変更しない。指定された場合は空文字を含めてそのまま保存する。
    curiosity: Optional[str] = None
    prior_thinking: Optional[str] = None

    @field_validator("draft_query")
    @classmethod
    def validate_draft_query(cls, v: str) -> str:
        if len(v) > 4000:
            raise ValueError("draft_query must be 4000 characters or less")
        return v

    @field_validator("curiosity", "prior_thinking")
    @classmethod
    def validate_ctqp_draft(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > CTQP_FIELD_MAX:
            raise ValueError(f"must be {CTQP_FIELD_MAX} characters or less")
        return v


class MessageOut(BaseModel):
    """Full snapshot of a message/analysis result, used to restore session state."""

    id: str
    session_id: str
    query: Optional[str] = None
    history: Optional[str] = None
    pro: list[str] = []
    con: list[str] = []
    recommendation: Optional[str] = None
    decision: Optional[str] = None
    decision_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    ai_recommendation_action: Optional[str] = None
    reason: Optional[str] = None
    target_date: Optional[date] = None
    log: Optional[str] = None
    risk_score: int = 0
    risk_category: list[str] = []
    response_confidence_score: int = 0
    response_confidence_level: str = "low"
    response_confidence_limiting_factors: list[str] = []
    created_at: datetime
    # G. 事前承認ワークフロー
    approval_status: Optional[str] = None  # "approved" | "rejected" | None(未申請/対象外)
    approved_by_name: Optional[str] = None
    approved_by_email: Optional[str] = None
    approval_comment: Optional[str] = None
    approved_at: Optional[datetime] = None
    addendum: Optional[str] = None
    addendum_updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    created_by: Optional[str] = None
    draft_query: Optional[str] = None
    # CTQP: C(きっかけ)/T(事前の考え)。既存セッションはNone(空欄/非表示)。
    curiosity: Optional[str] = None
    prior_thinking: Optional[str] = None
    # ダッシュボード一覧でステータス列の左側に表示するための、
    # 紐づくメッセージのTarget(実施ターゲット日)。
    target_date: Optional[date] = None
    messages: list[MessageOut] = []
    # G. フロントエンドがactive_org_id等から間接的に判定せずに済むよう、
    # バックエンドが直接「この閲覧者がこの組織の承認者か」を計算して返す。
    viewer_is_approver: bool = False
    # ダッシュボード一覧で「Approved Date」列として表示するための、
    # 紐づくメッセージの承認日時(未承認の場合はNone=空欄表示)。
    approved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SharedSessionOut(BaseModel):
    """組織内の他ユーザーが作成したセッションの一覧表示用(read-only対象)。"""

    id: str
    title: str
    status: str
    created_at: datetime
    created_by: str
    created_by_name: Optional[str] = None
    created_by_email: Optional[str] = None
    target_date: Optional[date] = None
    approved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DeleteSessionResponse(BaseModel):
    message: str = "削除しました"


class ApprovalQueueItem(BaseModel):
    """G. 承認者向け一覧: 承認が必要になったことがある(現在進行中/過去分とも)セッション1件分。"""

    session_id: str
    message_id: str
    title: str
    risk_score: int
    session_status: str
    created_by_name: Optional[str] = None
    latest_approved_at: Optional[datetime] = None
    latest_approved_by_name: Optional[str] = None
    latest_rejected_at: Optional[datetime] = None


class ApprovalQueueResponse(BaseModel):
    items: list[ApprovalQueueItem]


class PaginatedSessionResponse(BaseModel):
    """検索・フィルタ・ページネーション対応の一覧レスポンス(自分のログ)。"""

    items: list[SessionResponse]
    total: int
    page: int
    limit: int


class PaginatedSharedSessionOut(BaseModel):
    """検索・フィルタ・ページネーション対応の一覧レスポンス(組織内の他ユーザーのログ)。"""

    items: list[SharedSessionOut]
    total: int
    page: int
    limit: int
