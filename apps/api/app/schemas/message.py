from pydantic import BaseModel, field_validator
from typing import Optional
import re

# Disallowed patterns for whitelist input validation
_DISALLOWED = [
    re.compile(r"<[^>]+>", re.IGNORECASE),
    re.compile(r"(SELECT|INSERT|UPDATE|DELETE|DROP)\s", re.IGNORECASE),
    re.compile(r"ignore previous instructions", re.IGNORECASE),
    re.compile(r"(system\(|exec\(|eval\()", re.IGNORECASE),
]

HISTORY_MAX = 2000
PRO_CON_MAX_ITEMS = 5
PRO_CON_ITEM_MAX = 300
RECOMMENDATION_MAX = 1000
DECISION_MAX = 1000
REASON_MAX = 2000


class MessageInput(BaseModel):
    """User query sent to Gemini."""
    query: str
    history_context: Optional[str] = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        if len(v) > 4000:
            raise ValueError("Query must be 4000 characters or less")
        for pattern in _DISALLOWED:
            if pattern.search(v):
                raise ValueError("Query contains disallowed content")
        return v

    @field_validator("history_context")
    @classmethod
    def validate_history(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > HISTORY_MAX:
            raise ValueError(f"History must be {HISTORY_MAX} characters or less")
        return v


class DecisionInput(BaseModel):
    """Human records their final decision."""
    decision: str
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > REASON_MAX:
            raise ValueError(f"Reason must be {REASON_MAX} characters or less")
        for pattern in _DISALLOWED:
            if v and pattern.search(v):
                raise ValueError("Reason contains disallowed content")
        return v

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Decision cannot be empty")
        if len(v) > DECISION_MAX:
            raise ValueError(f"Decision must be {DECISION_MAX} characters or less")
        for pattern in _DISALLOWED:
            if pattern.search(v):
                raise ValueError("Decision contains disallowed content")
        return v


class HPCRDTLOutput(BaseModel):
    """Structured AI output with HPCRDTL schema."""
    history: str
    pro: list[str]
    con: list[str]
    recommendation: str
    risk_score: int
    risk_category: list[str]
    response_confidence: dict
    actor_type: str = "Human"
    relevant_preapproval_id: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    session_id: str
    query: str
    HPCRDTL_output: Optional[dict] = None
    decision: Optional[str] = None
    status: str

    model_config = {"from_attributes": True}
