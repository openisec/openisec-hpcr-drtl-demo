from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AuditLogOut(BaseModel):
    """org_<uuid>.audit_logs 1件分(組織アクティビティ)。"""

    id: str
    action: str
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    actor_type: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    target_user_id: Optional[str] = None
    target_user_email: Optional[str] = None
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    occurred_at: datetime


class PaginatedAuditLogResponse(BaseModel):
    """検索・フィルタ・ページネーション対応の一覧レスポンス(組織アクティビティ)。"""

    items: list[AuditLogOut]
    total: int
    page: int
    limit: int


class AuthAuditLogOut(BaseModel):
    """public.auth_audit_logs 1件分(認証ログ)。"""

    id: str
    action: str
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    org_id: Optional[str] = None
    org_name: Optional[str] = None
    target_user_id: Optional[str] = None
    detail: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    occurred_at: datetime


class PaginatedAuthAuditLogResponse(BaseModel):
    """検索・フィルタ・ページネーション対応の一覧レスポンス(認証ログ)。"""

    items: list[AuthAuditLogOut]
    total: int
    page: int
    limit: int


class AuditActionListResponse(BaseModel):
    """actionフィルタのドロップダウン用に、実際にログへ記録された action の一覧を返す。"""

    actions: list[str]
