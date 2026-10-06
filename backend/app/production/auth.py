"""High-entropy API key hashing and scope authorization."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.production.models import ApiKey, create_engine

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class ApiPrincipal:
    """Authenticated API caller."""

    key_id: str
    scopes: frozenset[str]


def generate_api_key() -> str:
    """Generate a credential with at least 256 bits of entropy."""
    locator = secrets.token_hex(8)
    return f"infd_{locator}_{secrets.token_urlsafe(32)}"


def api_key_locator(raw_key: str) -> str | None:
    """Extract the non-secret indexed locator from an API key."""
    parts = raw_key.split("_", 2)
    if len(parts) != 3 or parts[0] != "infd" or len(parts[1]) != 16:
        return None
    try:
        int(parts[1], 16)
    except ValueError:
        return None
    return parts[1]


def hash_api_key(raw_key: str, pepper: str) -> str:
    """Hash an API key using an application pepper and HMAC-SHA256."""
    if len(pepper) < 32:
        raise ValueError("API key pepper must contain at least 32 characters")
    return hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


class ApiKeyAuthenticator:
    """O(1) locator lookup followed by constant-time hash verification."""

    def __init__(self) -> None:
        self._records: dict[
            str,
            tuple[str, ApiPrincipal, datetime | None],
        ] = {}

    def register_hash(
        self,
        key_prefix: str,
        key_hash: str,
        principal: ApiPrincipal,
        expires_at: datetime | None = None,
    ) -> None:
        """Register a hashed key for memory/development operation."""
        self._records[key_prefix] = (key_hash, principal, expires_at)

    def verify(self, raw_key: str) -> ApiPrincipal | None:
        """Locate and verify a principal in constant expected time."""
        locator = api_key_locator(raw_key)
        if locator is None:
            return None
        record = self._records.get(locator)
        if record is None:
            return None
        stored_hash, principal, expires_at = record
        if expires_at is not None and expires_at <= datetime.now(UTC):
            return None
        candidate = hash_api_key(raw_key, settings.api_key_pepper)
        return principal if hmac.compare_digest(candidate, stored_hash) else None


authenticator = ApiKeyAuthenticator()
_auth_sessions: async_sessionmaker | None = None


def _get_auth_sessions() -> async_sessionmaker:
    global _auth_sessions
    if _auth_sessions is None:
        _auth_sessions = async_sessionmaker(create_engine(), expire_on_commit=False)
    return _auth_sessions


async def current_principal(
    raw_key: str | None = Security(API_KEY_HEADER),
) -> ApiPrincipal:
    """Authenticate the request or return a development principal."""
    if not settings.auth_required:
        return ApiPrincipal(key_id="development", scopes=frozenset({"*"}))
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing API key")
    if settings.persistence_backend == "postgres":
        locator = api_key_locator(raw_key)
        if locator is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid API key",
            )
        candidate = hash_api_key(raw_key, settings.api_key_pepper)
        sessions = _get_auth_sessions()
        async with sessions() as session:
            record = await session.scalar(
                select(ApiKey).where(
                    ApiKey.key_prefix == locator,
                    ApiKey.active.is_(True),
                )
            )
        principal = None
        expired = (
            record is not None
            and record.expires_at is not None
            and record.expires_at <= datetime.now(UTC)
        )
        if record and not expired and hmac.compare_digest(candidate, record.key_hash):
            principal = ApiPrincipal(key_id=record.id, scopes=frozenset(record.scopes))
    else:
        principal = authenticator.verify(raw_key)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    return principal


def require_scopes(*required: str):  # type: ignore[no-untyped-def]
    """Build a FastAPI dependency requiring all specified scopes."""

    async def dependency(
        principal: ApiPrincipal = Depends(current_principal),
    ) -> ApiPrincipal:
        if "*" not in principal.scopes and not set(required).issubset(principal.scopes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient scope")
        return principal

    return dependency


def require_any_scope(*allowed: str):  # type: ignore[no-untyped-def]
    """Build a FastAPI dependency accepting any one specified scope."""

    async def dependency(
        principal: ApiPrincipal = Depends(current_principal),
    ) -> ApiPrincipal:
        if "*" not in principal.scopes and principal.scopes.isdisjoint(allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient scope")
        return principal

    return dependency
