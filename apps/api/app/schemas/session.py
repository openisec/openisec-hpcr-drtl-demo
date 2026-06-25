from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import uuid


class SessionCreate(BaseModel):
    title: str
    decision_type_id: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Title must be 200 characters or less")
        return v.strip()


class SessionResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
