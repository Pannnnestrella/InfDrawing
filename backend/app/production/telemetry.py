"""Sanitized audit and provider-call persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import settings
from app.production.models import AuditLog, ProviderCall

_FORBIDDEN_DETAIL_KEYS = {
    "api_key",
    "authorization",
    "image",
    "image_bytes",
    "key",
    "payload",
    "prompt",
    "response",
}


class AuditEvent(BaseModel):
    """Sanitized ownership or lifecycle audit event."""

    actor_key_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProviderCallEvent(BaseModel):
    """Provider metadata without prompt or response contents."""

    job_id: str | None
    provider: str
    model: str
    latency_ms: int
    success: bool
    status_code: int | None = None
    error_code: str | None = None


class TelemetryRepository(Protocol):
    """Persistence contract for safe operational metadata."""

    async def audit(self, event: AuditEvent) -> None: ...

    async def provider_call(self, event: ProviderCallEvent) -> None: ...


class MemoryTelemetryRepository:
    """Inspectable development telemetry repository."""

    def __init__(self) -> None:
        self.audit_events: list[AuditEvent] = []
        self.provider_calls: list[ProviderCallEvent] = []

    async def audit(self, event: AuditEvent) -> None:
        """Retain a sanitized audit event."""
        self.audit_events.append(event)

    async def provider_call(self, event: ProviderCallEvent) -> None:
        """Retain provider metadata."""
        self.provider_calls.append(event)


class SqlTelemetryRepository:
    """PostgreSQL telemetry repository."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def audit(self, event: AuditEvent) -> None:
        """Insert a sanitized audit row."""
        async with self.sessions.begin() as session:
            session.add(
                AuditLog(
                    actor_key_id=event.actor_key_id,
                    action=event.action,
                    resource_type=event.resource_type,
                    resource_id=event.resource_id,
                    details=event.details,
                )
            )

    async def provider_call(self, event: ProviderCallEvent) -> None:
        """Insert provider-call metadata."""
        async with self.sessions.begin() as session:
            session.add(ProviderCall(**event.model_dump()))


def validate_audit_details(details: dict[str, Any]) -> dict[str, str | int | bool | None]:
    """Reject sensitive keys and non-scalar audit values."""
    safe: dict[str, str | int | bool | None] = {}
    for key, value in details.items():
        if key.lower() in _FORBIDDEN_DETAIL_KEYS:
            raise ValueError(f"sensitive audit detail is forbidden: {key}")
        if value is not None and not isinstance(value, (str, int, bool)):
            raise ValueError(f"audit detail must be scalar: {key}")
        safe[key] = value
    return safe


async def record_audit(
    actor_key_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an audit event after strict detail sanitization."""
    event = AuditEvent(
        actor_key_id=actor_key_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=validate_audit_details(details or {}),
    )
    await get_telemetry_repository().audit(event)


async def record_provider_call(event: ProviderCallEvent) -> None:
    """Persist provider metadata."""
    await get_telemetry_repository().provider_call(event)


_telemetry_repository: TelemetryRepository | None = None


def get_telemetry_repository() -> TelemetryRepository:
    """Return configured memory or PostgreSQL telemetry."""
    global _telemetry_repository
    if _telemetry_repository is None:
        if settings.persistence_backend == "postgres":
            from app.production.models import create_engine

            _telemetry_repository = SqlTelemetryRepository(create_engine())
        else:
            _telemetry_repository = MemoryTelemetryRepository()
    return _telemetry_repository
