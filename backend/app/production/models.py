"""Async SQLAlchemy persistence models for production services."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from app.config import Settings, settings


class Base(DeclarativeBase):
    """Declarative model base."""


class TimestampMixin:
    """Database-managed creation timestamp."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiKey(Base, TimestampMixin):
    """Hashed API credential with authorization scopes."""

    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120))
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base, TimestampMixin):
    """Durable asynchronous job and lease state."""

    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"))
    kind: Mapped[str] = mapped_column(String(64))
    queue: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        Index(
            "uq_jobs_owner_idempotency",
            "owner_key_id",
            "idempotency_key",
            unique=True,
            postgresql_where=idempotency_key.is_not(None),
        ),
    )


class JobEvent(Base, TimestampMixin):
    """Ordered job lifecycle event."""

    __tablename__ = "job_events"
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Artifact(Base, TimestampMixin):
    """Owner-bound object-storage artifact metadata."""

    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_key_id: Mapped[str] = mapped_column(ForeignKey("api_keys.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))


class ProviderCall(Base, TimestampMixin):
    """Provider call metadata without prompt or response contents."""

    __tablename__ = "provider_calls"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))


class AuditLog(Base, TimestampMixin):
    """Sanitized security and ownership audit event."""

    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    actor_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(120))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EditSessionRow(Base, TimestampMixin):
    """Controlled-edit session; ``data`` holds the serialized ``EditSession``."""

    __tablename__ = "edit_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key_id: Mapped[str] = mapped_column(ForeignKey("api_keys.id"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EditVersionRow(Base, TimestampMixin):
    """Controlled-edit version node; ``data`` holds the serialized ``EditVersion``."""

    __tablename__ = "edit_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("edit_sessions.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(24))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def create_engine(config: Settings = settings) -> AsyncEngine:
    """Create the production async database engine."""
    if not config.database_url:
        raise RuntimeError("database_url is required for PostgreSQL persistence")
    return create_async_engine(config.database_url, pool_pre_ping=True)


async def initialize_database(engine: AsyncEngine) -> None:
    """Create schema for development bootstrap; production uses migrations."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
