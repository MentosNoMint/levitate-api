from typing import Optional, List
from pydantic import BaseModel

class VirtualKeyCreate(BaseModel):
    user_id: Optional[str] = None
    name: str
    monthly_token_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    allowed_model_groups: Optional[List[str]] = None

class VirtualKeyUpdate(BaseModel):
    name: Optional[str] = None
    monthly_token_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    allowed_model_groups: Optional[List[str]] = None
    status: Optional[str] = None
