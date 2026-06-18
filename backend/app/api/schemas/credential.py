from typing import Optional, List
from pydantic import BaseModel

class CredentialCreate(BaseModel):
    type: str
    name: str
    provider: str
    secret: str
    base_url: Optional[str] = None
    models: Optional[List[str]] = None
    quota_total_tokens: Optional[int] = None
    quota_window: Optional[int] = None
    rpm_limit: Optional[int] = None
    concurrency_limit: Optional[int] = None
    priority: Optional[int] = 1
    weight: Optional[int] = 1

class CredentialUpdate(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    provider: Optional[str] = None
    secret: Optional[str] = None
    base_url: Optional[str] = None
    models: Optional[List[str]] = None
    quota_total_tokens: Optional[int] = None
    quota_window: Optional[int] = None
    rpm_limit: Optional[int] = None
    concurrency_limit: Optional[int] = None
    priority: Optional[int] = None
    weight: Optional[int] = None
    status: Optional[str] = None
