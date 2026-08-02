from typing import Optional, List
from pydantic import BaseModel, Field

class CredentialCreate(BaseModel):
    type: str
    name: str
    provider: str
    secret: str
    base_url: Optional[str] = None
    models: Optional[List[str]] = None
    quota_total_tokens: Optional[int] = Field(default=None, ge=0)
    quota_window: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    concurrency_limit: Optional[int] = Field(default=None, ge=0)
    priority: Optional[int] = Field(default=1, ge=0)
    weight: Optional[int] = Field(default=1, ge=0)

class CredentialUpdate(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    provider: Optional[str] = None
    secret: Optional[str] = None
    base_url: Optional[str] = None
    models: Optional[List[str]] = None
    quota_total_tokens: Optional[int] = Field(default=None, ge=0)
    quota_window: Optional[int] = Field(default=None, ge=0)
    rpm_limit: Optional[int] = Field(default=None, ge=0)
    concurrency_limit: Optional[int] = Field(default=None, ge=0)
    priority: Optional[int] = Field(default=None, ge=0)
    weight: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = None
