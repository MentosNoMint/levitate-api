from typing import Optional, List
from pydantic import BaseModel, Field

class VirtualKeyCreate(BaseModel):
    user_id: Optional[str] = None
    name: str
    monthly_token_limit: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    allowed_model_groups: Optional[List[str]] = None

class VirtualKeyUpdate(BaseModel):
    name: Optional[str] = None
    monthly_token_limit: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    allowed_model_groups: Optional[List[str]] = None
    status: Optional[str] = None
