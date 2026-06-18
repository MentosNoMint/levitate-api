from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy import String, Integer, BigInteger, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    virtual_keys: Mapped[List["VirtualKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    credentials: Mapped[List["Credential"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class VirtualKey(Base):
    __tablename__ = "virtual_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_token_limit: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    rpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowed_model_groups: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    user: Mapped["User"] = relationship(back_populates="virtual_keys")
    usage_events: Mapped[List["UsageEvent"]] = relationship(back_populates="virtual_key")

class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(String(2048), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    models: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    quota_total_tokens: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    quota_used_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    quota_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    concurrency_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    model_quotas: Mapped[Optional[Dict[str, float]]] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="credentials")
    usage_events: Mapped[List["UsageEvent"]] = relationship(back_populates="credential")

class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    virtual_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("virtual_keys.id", ondelete="SET NULL"), nullable=True)
    credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    virtual_key: Mapped[Optional["VirtualKey"]] = relationship(back_populates="usage_events")
    credential: Mapped[Optional["Credential"]] = relationship(back_populates="usage_events")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
